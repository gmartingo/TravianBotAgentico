/**
 * AttackReportsPage — Página raíz del módulo de reportes de ataques a oasis.
 *
 * Estructura:
 *   H1 "Reportes de oasis"
 *   TabBar (Ingresar | Historial | Estadísticas)
 *   <contenido del tab activo>
 *   ReportDetailDrawer (portal flotante)
 *
 * El tab activo se persiste en localStorage (DA-25).
 * El drawer se puede abrir desde la tab Ingresar (enlace a duplicado)
 * y desde la tab Historial (clic en fila).
 */
import { useState, useRef, useCallback } from 'react'
import { useI18n } from '../i18n/index.jsx'
import { TabBar } from '../components/ui/TabBar.jsx'
import { IngestTab } from '../components/attack-reports/IngestTab.jsx'
import { HistoryTab } from '../components/attack-reports/HistoryTab.jsx'
import { StatsTab }   from '../components/attack-reports/StatsTab.jsx'
import { ReportDetailDrawer } from '../components/attack-reports/ReportDetailDrawer.jsx'
import { api } from '../api/client.js'

const TAB_STORAGE_KEY = 'ar_active_tab'
const DEFAULT_TAB = 'ingest'

function getInitialTab() {
  try {
    return localStorage.getItem(TAB_STORAGE_KEY) ?? DEFAULT_TAB
  } catch {
    return DEFAULT_TAB
  }
}

export function AttackReportsPage() {
  const { t } = useI18n()
  const lang = (typeof localStorage !== 'undefined' && localStorage.getItem('lang')) || 'es'

  const [activeTab, setActiveTab] = useState(getInitialTab)
  const [drawerReportId, setDrawerReportId] = useState(null)
  const drawerReturnRef = useRef(null)

  function handleTabChange(id) {
    setActiveTab(id)
    try { localStorage.setItem(TAB_STORAGE_KEY, id) } catch { /* ignorar */ }
  }

  function openDrawer(id, returnRef = null) {
    drawerReturnRef.current = returnRef?.current ?? null
    setDrawerReportId(id)
  }

  function closeDrawer() {
    setDrawerReportId(null)
  }

  async function handleDrawerDelete(id) {
    await api.deleteAttackReport(id)
  }

  const tabs = [
    { id: 'ingest',  label: t('ar.tab.ingest') },
    { id: 'history', label: t('ar.tab.history') },
    { id: 'stats',   label: t('ar.tab.stats') },
  ]

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '1100px' }}>
      {/* H1 */}
      <h1 style={{ margin: 0, fontSize: '22px', fontWeight: 600, color: 'var(--text)' }}>
        {t('ar.page.title')}
      </h1>

      {/* TabBar */}
      <TabBar
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        panelId={(id) => `ar-tabpanel-${id}`}
      />

      {/* Panel de tab activo */}
      <div>
        {/* Ingresar */}
        <div
          id="ar-tabpanel-ingest"
          role="tabpanel"
          aria-labelledby="tab-ingest"
          hidden={activeTab !== 'ingest'}
        >
          {activeTab === 'ingest' && (
            <IngestTab
              onOpenDrawer={(id) => openDrawer(id)}
              lang={lang}
            />
          )}
        </div>

        {/* Historial */}
        <div
          id="ar-tabpanel-history"
          role="tabpanel"
          aria-labelledby="tab-history"
          hidden={activeTab !== 'history'}
        >
          {activeTab === 'history' && (
            <HistoryTab
              onOpenDrawer={(id) => openDrawer(id)}
              lang={lang}
              onSwitchTab={handleTabChange}
            />
          )}
        </div>

        {/* Estadísticas */}
        <div
          id="ar-tabpanel-stats"
          role="tabpanel"
          aria-labelledby="tab-stats"
          hidden={activeTab !== 'stats'}
        >
          {activeTab === 'stats' && (
            <StatsTab lang={lang} onGoToIngest={() => handleTabChange('ingest')} />
          )}
        </div>
      </div>

      {/* Drawer de detalle (accesible desde cualquier tab) */}
      <ReportDetailDrawer
        reportId={drawerReportId}
        onClose={closeDrawer}
        onDelete={handleDrawerDelete}
        returnRef={drawerReturnRef}
        lang={lang}
      />
    </div>
  )
}
