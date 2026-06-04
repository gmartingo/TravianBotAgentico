/**
 * NoiseTab — Pestaña "Ruido" dentro de WorldSpacePage.
 *
 * Orquesta la carga inicial (EP-N01 + EP-N03 en paralelo) y pasa los datos
 * a los subcomponentes:
 *  - NoiseConfigPanel   (config global)
 *  - NoiseDestinationsTable (tabla de destinos)
 *  - NoiseDestinationDrawer (drawer lateral)
 *
 * Optimización de rendimiento (apertura del drawer):
 *  - Los orígenes (EP-N12) se cargan aquí una sola vez y se pasan al wizard
 *    como prop, evitando un nuevo fetch en cada apertura/remontaje del drawer.
 *  - El drawer se mantiene montado en el DOM (visible: hidden cuando cerrado)
 *    para evitar el desmontaje/remontaje completo del subárbol en cada apertura.
 *
 * Props:
 *  - worldId {number}
 *
 * Spec: docs/design/noise-catalog-ui.md §3, §7
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useI18n } from '../../../i18n/index.jsx'
import { api, ApiError } from '../../../api/client.js'
import { Spinner, showToast } from '../../ui/uiUtils.jsx'
import { NoiseConfigPanel } from './NoiseConfigPanel.jsx'
import { NoiseDestinationsTable } from './NoiseDestinationsTable.jsx'
import { NoiseDestinationDrawer } from './NoiseDestinationDrawer.jsx'

// ── Skeleton del tab ──────────────────────────────────────────────────────────

function SkeletonTab() {
  const pulse = {
    background: 'var(--surface-2)',
    borderRadius: 'var(--radius-sm)',
    animation: 'skeleton-pulse 1.4s ease-in-out infinite',
  }
  return (
    <>
      <style>{`@keyframes skeleton-pulse{0%,100%{opacity:1}50%{opacity:.45}}`}</style>
      {/* Config panel skeleton */}
      <div style={{ ...pulse, height: '44px', marginBottom: '16px', borderRadius: 'var(--radius-md)' }} />
      {/* Table skeleton */}
      <div style={{ ...pulse, height: '32px', marginBottom: '10px' }} />
      {[1, 2, 3].map(i => (
        <div key={i} style={{ ...pulse, height: '48px', marginBottom: '6px' }} />
      ))}
    </>
  )
}

// ── NoiseTab ──────────────────────────────────────────────────────────────────

export function NoiseTab({ worldId }) {
  const { t } = useI18n()

  const [config, setConfig] = useState(null)
  const [destinations, setDestinations] = useState([])
  const [loading, setLoading] = useState(true)
  const [apiError, setApiError] = useState(null)

  // Drawer
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerDest, setDrawerDest] = useState(null)
  const drawerTriggerRef = useRef(null)

  // Orígenes (EP-N12) cargados una sola vez a nivel de tab para evitar
  // re-fetch en cada apertura del drawer (el wizard los recibe como prop).
  const [origins, setOrigins] = useState(null)
  const [loadingOrigins, setLoadingOrigins] = useState(false)
  const [originsError, setOriginsError] = useState(null)

  const loadOrigins = useCallback(async () => {
    setLoadingOrigins(true)
    setOriginsError(null)
    try {
      const data = await api.getNoiseOrigins(worldId)
      setOrigins(data)
    } catch (e) {
      setOriginsError(e instanceof ApiError ? e.detail : t('noise.wizard.originLoadError'))
    } finally {
      setLoadingOrigins(false)
    }
  }, [worldId]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadAll = useCallback(async () => {
    setLoading(true)
    setApiError(null)
    try {
      const [cfgData, destData] = await Promise.all([
        api.getNoiseConfig(worldId),
        api.getNoiseDestinations(worldId),
      ])
      setConfig(cfgData)
      setDestinations(destData?.destinations ?? destData ?? [])
    } catch (e) {
      setApiError(e instanceof ApiError ? e.detail : t('noise.destinations.error'))
    } finally {
      setLoading(false)
    }
  }, [worldId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadAll()
    // Pre-cargar orígenes en paralelo con la carga principal, sin bloquear el skeleton
    loadOrigins()
  }, [loadAll, loadOrigins])

  // Callbacks estabilizados con useCallback para que React.memo en los hijos
  // (NoiseConfigPanel, NoiseDestinationsTable) evite re-renders cuando solo
  // cambia el estado del drawer (drawerOpen, drawerDest).
  const openDrawer = useCallback((dest, triggerEl) => {
    drawerTriggerRef.current = triggerEl ?? null
    setDrawerDest(dest)
    setDrawerOpen(true)
  }, [])

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false)
    setDrawerDest(null)
  }, [])

  const handleDestCreated = useCallback((dest) => {
    setDestinations(prev => [dest, ...prev])
  }, [])

  const handleDestDeleted = useCallback((id) => {
    setDestinations(prev => prev.filter(d => d.id !== id))
    // Si el drawer está abierto para este destino, cerrarlo
    setDrawerDest(prev => {
      if (prev?.id === id) { setDrawerOpen(false); return null }
      return prev
    })
  }, [])

  const handleDestUpdated = useCallback((updated) => {
    setDestinations(prev => prev.map(d => d.id === updated.id ? updated : d))
    setDrawerDest(prev => prev?.id === updated.id ? updated : prev)
  }, [])

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) return <SkeletonTab />

  if (apiError) {
    return (
      <div style={{ textAlign: 'center', padding: '48px 24px' }}>
        <p style={{ fontSize: '14px', color: 'var(--danger)', marginBottom: '12px' }}>{apiError}</p>
        <button
          type="button"
          onClick={loadAll}
          style={{
            height: '34px', padding: '0 16px',
            border: '1px solid var(--border-strong)',
            background: 'var(--surface)', color: 'var(--text)',
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'inherit', fontSize: '13px',
            cursor: 'pointer',
          }}
        >
          {t('noise.destinations.retry')}
        </button>
      </div>
    )
  }

  return (
    <div>
      {/* Panel config global (P2, colapsado por defecto) */}
      <NoiseConfigPanel
        config={config}
        loading={false}
        onSaved={setConfig}
        worldId={worldId}
      />

      {/* Tabla de destinos */}
      <NoiseDestinationsTable
        worldId={worldId}
        destinations={destinations}
        loading={false}
        onOpenDrawer={openDrawer}
        onDeleted={handleDestDeleted}
        onCreated={handleDestCreated}
      />

      {/* Drawer lateral — siempre montado; visibility controlada internamente
          para evitar desmontaje/remontaje del subárbol en cada apertura */}
      <NoiseDestinationDrawer
        open={drawerOpen}
        dest={drawerDest}
        worldId={worldId}
        onClose={closeDrawer}
        triggerRef={drawerTriggerRef}
        onDestUpdated={handleDestUpdated}
        origins={origins}
        loadingOrigins={loadingOrigins}
        originsError={originsError}
        onOriginsRefreshed={setOrigins}
        onRetryOrigins={loadOrigins}
      />
    </div>
  )
}
