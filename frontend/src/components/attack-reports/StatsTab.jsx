/**
 * StatsTab — Pestaña "Estadísticas" del módulo de reportes de oasis.
 *
 * Layout (DA-CL01: BalanceSection ANTES de GlobalOasisStatsPanel):
 *   1. BalanceSection        — bloque KPI (carga independiente de EP-BALANCE).
 *   2. GlobalOasisStatsPanel — panel fijo siempre visible (carga independiente).
 *   3. OasisList             — lista de oasis individuales (carga independiente).
 *
 * Las tres cargas son paralelas: un error en cualquiera NO bloquea las otras.
 * DA-CL08/09: BalanceSection falla de forma aislada.
 */
import { useState, useEffect, useCallback } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api } from '../../api/client.js'
import { OasisList } from './OasisList.jsx'
import { GlobalOasisStatsPanel } from './GlobalOasisStatsPanel.jsx'
import { BalanceSection } from './BalanceSection.jsx'

export function StatsTab({ lang, onGoToIngest }) {
  const { t } = useI18n()

  // ── Estado del panel global (independiente de OasisList y Balance) ─────────
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
      {/* 1. BalanceSection — DA-CL01: SIEMPRE encima del panel global */}
      <BalanceSection lang={lang} t={t} />

      {/* 2. Panel global */}
      <GlobalOasisStatsPanel
        data={globalData}
        loading={globalLoading}
        error={globalError}
        onRetry={loadGlobal}
        onGoToIngest={onGoToIngest}
        lang={lang}
        t={t}
      />

      {/* 3. Lista de oasis individuales */}
      <OasisList
        lang={lang}
        onGoToIngest={onGoToIngest}
        t={t}
      />
    </div>
  )
}
