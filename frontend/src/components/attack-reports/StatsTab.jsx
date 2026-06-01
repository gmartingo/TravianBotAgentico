/**
 * StatsTab — Pestaña "Estadísticas" del módulo de reportes de oasis.
 *
 * Layout:
 *   1. GlobalOasisStatsPanel — panel fijo siempre visible (carga independiente).
 *   2. OasisList             — lista de oasis individuales (carga independiente).
 *
 * Las dos cargas son paralelas: un error del panel global NO bloquea OasisList.
 *
 * Props:
 *   lang         — string (idioma activo)
 *   onGoToIngest — () => void — callback para navegar a la pestaña Ingresar
 *                  (CTA del estado vacío y navegación desde OasisList)
 *
 * Ver spec docs/specs/bd-ataques-oasis-stats-global.md §9 StatsTab.
 */
import { useState, useEffect, useCallback } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api } from '../../api/client.js'
import { OasisList } from './OasisList.jsx'
import { GlobalOasisStatsPanel } from './GlobalOasisStatsPanel.jsx'

export function StatsTab({ lang, onGoToIngest }) {
  const { t } = useI18n()

  // ── Estado del panel global (independiente de OasisList) ──────────────────
  const [globalData, setGlobalData]       = useState(null)
  const [globalLoading, setGlobalLoading] = useState(true)
  const [globalError, setGlobalError]     = useState(null)

  const loadGlobal = useCallback(async () => {
    setGlobalLoading(true)
    setGlobalError(null)
    try {
      const res = await api.getGlobalOasisStats()
      setGlobalData(res)
    } catch (err) {
      setGlobalError(err?.detail ?? t('ar.stats.global.error'))
    } finally {
      setGlobalLoading(false)
    }
  }, [t])

  useEffect(() => { loadGlobal() }, [loadGlobal])

  return (
    <div style={{ maxWidth: '900px' }}>
      {/* Panel global — SIEMPRE encima de OasisList */}
      <GlobalOasisStatsPanel
        data={globalData}
        loading={globalLoading}
        error={globalError}
        onRetry={loadGlobal}
        onGoToIngest={onGoToIngest}
        lang={lang}
        t={t}
      />

      {/* Separador visual (24px) ya incluido via marginBottom del panel */}
      <OasisList
        lang={lang}
        onGoToIngest={onGoToIngest}
        t={t}
      />
    </div>
  )
}
