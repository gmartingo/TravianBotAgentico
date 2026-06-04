/**
 * NoiseOriginSelector — Desplegable de anclas semilla para el wizard.
 *
 * Props:
 *  - worldId       {number}
 *  - origins       {object|null}  — respuesta de EP-N12: { generic_origins, village_origins, villages_loaded }
 *  - loading       {boolean}
 *  - loadError     {string|null}
 *  - value         {string}       — origen seleccionado actualmente
 *  - onChange      {Function(value, label)} — cuando cambia la selección
 *  - onRetry       {Function}     — recargar origins
 *  - onRefreshed   {Function(origins)} — callback tras refresh-villages con éxito
 *  - disabled      {boolean}
 *
 * Spec: docs/design/noise-catalog-ui.md §6 (Wizard paso 0), §7
 */
import { useState } from 'react'
import { useI18n } from '../../../i18n/index.jsx'
import { api, ApiError } from '../../../api/client.js'
import { Spinner } from '../../ui/uiUtils.jsx'

function IconRefresh({ size = 12 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 .49-4.95" />
    </svg>
  )
}

export function NoiseOriginSelector({ worldId, origins, loading, loadError, value, onChange, onRetry, onRefreshed, disabled }) {
  const { t } = useI18n()
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState(null)

  const genericOrigins = origins?.generic_origins ?? []
  const villageOrigins = origins?.village_origins ?? []
  const villagesLoaded = origins?.villages_loaded ?? false

  async function handleRefreshVillages() {
    setRefreshing(true)
    setRefreshError(null)
    try {
      const data = await api.refreshNoiseVillages(worldId)
      // Rebuild origins with updated villages
      const newOrigins = {
        ...(origins ?? {}),
        village_origins: (data.villages_data ?? []).map(v => ({
          value: `VILLAGE_${v.data_id}`,
          label: v.name,
          data_id: v.data_id,
          x: v.x,
          y: v.y,
          path: `/dorf1.php?newdid=${v.data_id}`,
        })),
        villages_loaded: (data.villages_found ?? 0) > 0,
      }
      onRefreshed(newOrigins)
      // Mostrar toast — no importamos showToast aquí para evitar dep circular
      // El padre lo recibe vía onRefreshed
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setRefreshError(t('noise.wizard.refreshError409'))
      } else if (e instanceof ApiError) {
        setRefreshError(e.detail ?? t('noise.wizard.refreshError'))
      } else {
        setRefreshError(t('noise.wizard.refreshError'))
      }
    } finally {
      setRefreshing(false)
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-tertiary)', fontSize: '13px' }}>
        <Spinner size={13} />
        {t('noise.wizard.originLoading')}
      </div>
    )
  }

  if (loadError) {
    return (
      <div style={{ fontSize: '13px', color: 'var(--danger)' }}>
        {loadError}
        <button
          type="button"
          onClick={onRetry}
          style={{
            marginInlineStart: '8px',
            appearance: 'none', border: 'none', background: 'transparent',
            color: 'var(--accent-text)', cursor: 'pointer',
            fontFamily: 'inherit', fontSize: '13px', textDecoration: 'underline',
          }}
        >
          {t('noise.wizard.originRetry')}
        </button>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <select
        value={value}
        onChange={e => {
          const v = e.target.value
          // Encontrar el label del seleccionado
          const gen = genericOrigins.find(o => o.value === v)
          const vil = villageOrigins.find(o => o.value === v)
          const label = gen?.label ?? vil?.label ?? v
          onChange(v, label)
        }}
        disabled={disabled}
        aria-label={t('noise.wizard.originField')}
        style={{
          padding: '6px 8px',
          border: '1px solid var(--border-strong)',
          borderRadius: 'var(--radius-sm)',
          background: 'var(--surface)', color: 'var(--text)',
          fontFamily: 'inherit', fontSize: '13px',
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.7 : 1,
        }}
      >
        <optgroup label={t('noise.origin.genericGroup')}>
          {genericOrigins.map(o => (
            <option key={o.value} value={o.value}>
              {t(`noise.origin.${o.value}`) || o.label}
            </option>
          ))}
        </optgroup>

        {(villagesLoaded && villageOrigins.length > 0) ? (
          <optgroup label={t('noise.origin.villageGroup')}>
            {villageOrigins.map(o => (
              <option key={o.value} value={o.value}>
                {o.label} — /dorf1.php?newdid={o.data_id}
              </option>
            ))}
          </optgroup>
        ) : null}
      </select>

      {/* Sección aldeas: vacía o con botón refresh */}
      {!villagesLoaded && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
            {t('noise.wizard.noVillages')}
          </span>
          <button
            type="button"
            onClick={handleRefreshVillages}
            disabled={refreshing || disabled}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '5px',
              height: '26px', padding: '0 10px',
              border: '1px solid var(--border-strong)',
              background: 'var(--surface)', color: 'var(--text-secondary)',
              borderRadius: 'var(--radius-sm)',
              fontFamily: 'inherit', fontSize: '12px',
              cursor: (refreshing || disabled) ? 'not-allowed' : 'pointer',
              opacity: (refreshing || disabled) ? 0.7 : 1,
            }}
          >
            {refreshing ? <Spinner size={11} /> : <IconRefresh size={11} />}
            {refreshing ? t('noise.wizard.refreshingVillages') : t('noise.wizard.refreshVillages')}
          </button>
        </div>
      )}

      {/* Error de refresh (409 u otros) */}
      {refreshError && (
        <p role="alert" style={{ fontSize: '12px', color: 'var(--danger)', margin: 0 }}>
          {refreshError}
        </p>
      )}
    </div>
  )
}
