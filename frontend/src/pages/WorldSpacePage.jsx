/**
 * WorldSpacePage — S9 Espacio del mundo (implementación real).
 *
 * Shell:
 *  - Topbar fija (← Mundos | TB TravianBot | ThemeToggle | LangPicker)
 *  - World-header: email en oro + badge "Activo" / server · tribu
 *  - Sidebar izquierda (180px = --sidebar-w): Dashboard · Agentes · Listas de vacas · Calculadora
 *  - Contenido de pestaña (padding-bottom:72px para la barra fija)
 *  - AgentBottomBar fija en bottom:0
 *
 * Pestañas:
 *  - Agentes (default) → AgentsTab (V1: panel agente + schedulers + modales V2/V3)
 *  - Listas de vacas   → FarmListsTab (V4) + FarmListDrawer (V5/V6)
 *  - Dashboard / Calculadora → "próximamente"
 *
 * Datos cargados:
 *  - GET /accounts → buscar el mundo (worldId) en todas las cuentas → obtener email + server + tribe
 *  - GET /farm/worlds/:worldId/agent/status → agentStatus (polling 10s)
 *  - GET /farm/worlds/:worldId/schedulers   → schedulers
 *  - GET /farm/worlds/:worldId/farm-lists   → farmLists
 *
 * Spec: docs/design/farm-lists-ui.md
 * Mockup aprobado: frontend/mockups/farm-lists.playground.html
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useI18n } from '../i18n/index.jsx'
import { api, ApiError } from '../api/client.js'
import { parseServerUrl, showToast, ErrorBoundary } from '../components/ui/uiUtils.jsx'
import { ThemeToggle } from '../components/ui/ThemeToggle.jsx'
import { LangPicker }  from '../components/ui/LangPicker.jsx'
import { AgentsTab }   from '../components/world/AgentsTab.jsx'
import { SchedulerDashboard } from '../components/world/SchedulerDashboard.jsx'
import { FarmListsTab }   from '../components/world/FarmListsTab.jsx'
import { FarmListDrawer } from '../components/world/FarmListDrawer.jsx'
import { AgentBottomBar } from '../components/world/AgentBottomBar.jsx'
import { SessionTab }     from '../components/session/SessionTab.jsx'
import { NoiseTab }       from '../components/world/noise/NoiseTab.jsx'

// ── Iconos sidebar ────────────────────────────────────────────────────────────

function IconDashboard() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '16px', height: '16px', flexShrink: 0 }} aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
    </svg>
  )
}

function IconAgents() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '16px', height: '16px', flexShrink: 0 }} aria-hidden="true">
      <rect x="7" y="7" width="10" height="10" rx="1" />
      <path d="M16 16l2 2M16 8l2-2M8 16l-2 2M8 8l-2-2M12 7V3M12 21v-4M7 12H3M21 12h-4" />
    </svg>
  )
}

function IconLists() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '16px', height: '16px', flexShrink: 0 }} aria-hidden="true">
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" />
      <line x1="3" y1="12" x2="3.01" y2="12" />
      <line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  )
}

function IconCalc() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '16px', height: '16px', flexShrink: 0 }} aria-hidden="true">
      <rect x="4" y="2" width="16" height="20" rx="2" />
      <line x1="8" y1="6" x2="16" y2="6" />
      <line x1="8" y1="12" x2="10" y2="12" />
      <line x1="14" y1="12" x2="16" y2="12" />
      <line x1="8" y1="16" x2="10" y2="16" />
      <line x1="14" y1="16" x2="16" y2="16" />
    </svg>
  )
}

function IconSession() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '16px', height: '16px', flexShrink: 0 }} aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15 15" />
    </svg>
  )
}

function IconNoise() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '16px', height: '16px', flexShrink: 0 }} aria-hidden="true">
      <path d="M5 12.5 a9 9 0 0 1 14 0" />
      <path d="M8 15.5 a5 5 0 0 1 8 0" />
      <circle cx="12" cy="18" r="1" fill="currentColor" stroke="none" />
    </svg>
  )
}

// Constante que debe coincidir con el CSS --sidebar-w del token
const SIDEBAR_W = 180

// ── WorldSpacePage ────────────────────────────────────────────────────────────

export function WorldSpacePage() {
  const { worldId: worldIdStr } = useParams()
  const worldId = Number(worldIdStr)
  const navigate = useNavigate()
  const { t } = useI18n()

  // Pestaña activa: "agents" (default según DA-01), "farmlists", "dashboard", "calc"
  const [activeTab, setActiveTab] = useState('agents')
  const [highlightFarmListId, setHighlightFarmListId] = useState(null)

  // Drill-down al SchedulerDashboard (v10): scheduler seleccionado, o null = lista
  const [schedulerDashboard, setSchedulerDashboard] = useState(null)

  function handleNavigateToFarmList(farmListId) {
    setHighlightFarmListId(farmListId)
    setActiveTab('farmlists')
    // Si las farm lists aún no se cargaron, fetchFarmLists se dispara por el useEffect de activeTab
  }

  // Datos del mundo (resueltos buscando en las cuentas del usuario)
  const [worldInfo, setWorldInfo] = useState(null) // { email, server, tribe }

  // Estado del agente
  const [agentStatus, setAgentStatus] = useState(null)
  const agentState = agentStatus?.state ?? 'stopped'

  // Schedulers
  const [schedulers, setSchedulers] = useState([])
  const [loadingSchedulers, setLoadingSchedulers] = useState(true)
  const schedulersInitialized = useRef(false)

  // Farm lists
  const [farmLists, setFarmLists] = useState([])
  const [loadingFarmLists, setLoadingFarmLists] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [lastSyncTime, setLastSyncTime] = useState(null)

  // Drawer V5
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerFarmList, setDrawerFarmList] = useState(null)
  const drawerTriggerRef = useRef(null)

  // ── Carga inicial: info del mundo + agente + schedulers ──────────────────

  useEffect(() => {
    // 1. Obtener info del mundo (email de la cuenta, server, tribe)
    api.getAccounts().then(accounts => {
      for (const acc of accounts) {
        const world = acc.worlds?.find(w => w.id === worldId)
        if (world) {
          setWorldInfo({ email: acc.email, server: world.server, tribe: world.tribe })
          break
        }
      }
    }).catch(() => {/* silencioso: no bloquea la UI */})

    // 2. Agente
    fetchAgentStatus()

    // 3. Schedulers
    fetchSchedulers()

    // 4. Farm lists (eager: necesario para que los chips del scheduler muestren nombres)
    fetchFarmLists()
  }, [worldId])

  // Polling del agente cada 10s
  useEffect(() => {
    const id = setInterval(fetchAgentStatus, 10_000)
    return () => clearInterval(id)
  }, [worldId])

  // Polling de schedulers cada 30s (fallback)
  useEffect(() => {
    const id = setInterval(fetchSchedulers, 30_000)
    return () => clearInterval(id)
  }, [worldId])

  // Recarga inmediata de schedulers cuando next_task_at cambia:
  // señal de que el agente ejecutó una tarea y la reencoló con nuevo next_run.
  const prevNextTaskAt = useRef(null)
  useEffect(() => {
    const nextAt = agentStatus?.next_task_at ?? null
    if (nextAt !== prevNextTaskAt.current) {
      prevNextTaskAt.current = nextAt
      if (nextAt !== null) fetchSchedulers()
    }
  }, [agentStatus?.next_task_at])

  async function fetchAgentStatus() {
    try {
      const data = await api.getAgentStatus(worldId)
      setAgentStatus(data)
      // Si next_task_at ya venció, el agente debería haber ejecutado pronto —
      // refrescar schedulers para capturar el nuevo next_run sin esperar al poll de 30s.
      if (data?.next_task_at && new Date(data.next_task_at) < new Date()) {
        fetchSchedulers()
      }
    } catch {
      // Error de red: dejar agentStatus como null (UI muestra stopped)
    }
  }

  async function fetchSchedulers() {
    if (!schedulersInitialized.current) setLoadingSchedulers(true)
    try {
      const data = await api.getSchedulers(worldId)
      setSchedulers(data?.schedulers ?? data ?? [])
      schedulersInitialized.current = true
    } catch {
      showToast(t('error.loadFailed'))
    } finally {
      setLoadingSchedulers(false)
    }
  }

  // ── Carga de farm lists (solo cuando se activa la pestaña) ───────────────

  useEffect(() => {
    if (activeTab === 'farmlists' && farmLists.length === 0) {
      fetchFarmLists()
    }
  }, [activeTab])

  async function fetchFarmLists() {
    setLoadingFarmLists(true)
    try {
      const data = await api.getFarmLists(worldId)
      const lists = data?.farm_lists ?? data ?? []
      setFarmLists(lists)
      if (lists.length > 0) {
        // Usar el campo de última sincronización si la API lo expone; si no, ahora
        setLastSyncTime(data?.last_sync ?? new Date().toISOString())
      }
    } catch {
      showToast(t('farmLists.error.syncFailed'))
    } finally {
      setLoadingFarmLists(false)
    }
  }

  async function handleSyncNow() {
    setSyncing(true)
    try {
      await api.readFarmLists(worldId)
      await fetchFarmLists()
      setLastSyncTime(new Date().toISOString())
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('farmLists.error.syncFailed'))
    } finally {
      setSyncing(false)
    }
  }

  // ── Acciones del agente ──────────────────────────────────────────────────

  async function handleAgentStart() {
    try {
      await api.startAgent(worldId)
      await fetchAgentStatus()
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('agent.error.startFailed'))
    }
  }

  async function handleAgentStop() {
    try {
      await api.stopAgent(worldId)
      await fetchAgentStatus()
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('agent.error.stopFailed'))
    }
  }

  async function handleToggleAgent() {
    if (agentState === 'running') {
      await handleAgentStop()
    } else {
      await handleAgentStart()
    }
  }

  // ── Drawer ───────────────────────────────────────────────────────────────

  function openDrawer(farmList, triggerEl) {
    drawerTriggerRef.current = triggerEl ?? null
    setDrawerFarmList(farmList)
    setDrawerOpen(true)
  }

  function closeDrawer() {
    setDrawerOpen(false)
    setDrawerFarmList(null)
  }

  // ── Callbacks de cambio ──────────────────────────────────────────────────

  function handleSchedulersChange() {
    fetchSchedulers()
  }

  // ── Info del servidor (legible) ──────────────────────────────────────────

  const parsedServer = worldInfo?.server ? parseServerUrl(worldInfo.server) : null
  const tribeKey = worldInfo?.tribe ? `tribe.${worldInfo.tribe}` : null
  const tribeLabel = tribeKey ? t(tribeKey) : null

  // ── Scheduler name para el drawer ────────────────────────────────────────

  function getSchedulerName(schedulerId) {
    if (!schedulerId) return null
    return schedulers.find(s => s.id === schedulerId)?.name ?? null
  }

  // ── Tasks para el AgentBottomBar ─────────────────────────────────────────
  // Se construyen desde los schedulers activos (la API de status solo expone el conteo).
  // Cuando el agente está parado no se muestran tareas.

  const bottomBarTasks = agentState === 'running'
    ? schedulers
        .filter(s => s.is_enabled && s.next_run)
        .map(s => ({
          id: s.id,
          list_name: s.name,
          next_run_iso: s.next_run,
          sched_name: s.name,
        }))
    : []

  // ── Nav items ────────────────────────────────────────────────────────────

  const navItems = [
    {
      id: 'dashboard',
      label: t('worldnav.dashboard'),
      icon: <IconDashboard />,
      disabled: false,
      soon: false,
    },
    {
      id: 'agents',
      label: t('worldnav.agents'),
      icon: <IconAgents />,
      disabled: false,
      soon: false,
    },
    {
      id: 'farmlists',
      label: t('worldnav.farmLists'),
      icon: <IconLists />,
      disabled: false,
      soon: false,
    },
    {
      id: 'session',
      label: t('worldnav.session'),
      icon: <IconSession />,
      disabled: false,
      soon: false,
    },
    {
      id: 'noise',
      label: t('worldnav.noise'),
      icon: <IconNoise />,
      disabled: false,
      soon: false,
    },
    {
      id: 'calc',
      label: t('worldnav.calculator'),
      icon: <IconCalc />,
      disabled: true,
      soon: true,
    },
  ]

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100%',
      background: 'var(--bg)',
    }}>

      {/* ── Topbar ── */}
      <header style={{
        display: 'flex', alignItems: 'center', gap: '12px',
        padding: '0 20px', height: '52px', flexShrink: 0,
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
        zIndex: 50,
      }}
        role="banner"
      >
        {/* Wordmark clicable → volver a mundos */}
        <button
          type="button"
          onClick={() => navigate(-1)}
          aria-label={t('topbar.backToWorlds')}
          style={{
            appearance: 'none', border: 'none', background: 'transparent',
            cursor: 'pointer', padding: 0, flexShrink: 0,
            display: 'flex', alignItems: 'center', gap: '8px',
            fontWeight: 600, fontSize: '15px', color: 'var(--text)',
            fontFamily: 'inherit',
            transition: 'opacity var(--dur-fast)',
          }}
          onMouseEnter={e => { e.currentTarget.style.opacity = '0.75' }}
          onMouseLeave={e => { e.currentTarget.style.opacity = '1' }}
        >
          <div style={{
            width: '28px', height: '28px',
            borderRadius: '7px',
            background: 'var(--btn-primary-bg)',
            color: 'var(--btn-primary-text)',
            display: 'grid', placeItems: 'center',
            fontWeight: 700, fontSize: '12px',
            flexShrink: 0,
          }} aria-hidden="true">
            TB
          </div>
          <span className="hidden sm:inline">{t('app.name')}</span>
        </button>

        {/* Centro: email · server · tribe · • Activo — una sola fila */}
        <div style={{
          flex: 1,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: '6px', overflow: 'hidden',
        }}>
          <span style={{
            fontSize: '13px', fontWeight: 500,
            color: 'var(--accent-text)',
            fontFamily: 'var(--font-mono)',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            maxWidth: '220px',
          }}>
            {worldInfo?.email ?? '…'}
          </span>

          <span style={{ color: 'var(--text-disabled)', flexShrink: 0 }}>·</span>

          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '4px',
            fontSize: '12px', fontWeight: 500,
            color: 'var(--success)', flexShrink: 0,
          }}>
            <span style={{
              width: '6px', height: '6px',
              borderRadius: '50%', background: 'currentColor', flexShrink: 0,
            }} aria-hidden="true" />
            {t('world.badge.active')}
          </span>

          {(parsedServer || tribeLabel) && (
            <>
              <span style={{ color: 'var(--text-disabled)', flexShrink: 0 }}>·</span>
              {parsedServer && (
                <span style={{
                  fontSize: '13px', color: 'var(--text-secondary)',
                  fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap', flexShrink: 0,
                }}>
                  {parsedServer}
                </span>
              )}
              {parsedServer && tribeLabel && (
                <span style={{ color: 'var(--text-disabled)', flexShrink: 0 }}>·</span>
              )}
              {tribeLabel && (
                <span style={{ fontSize: '13px', color: 'var(--text-secondary)', whiteSpace: 'nowrap', flexShrink: 0 }}>
                  {tribeLabel}
                </span>
              )}
            </>
          )}
        </div>

        <ThemeToggle />
        <LangPicker />
      </header>

      {/* ── App body: sidebar + contenido — envuelto en ErrorBoundary de recuperación ── */}
      <ErrorBoundary onReset={() => navigate(-1)} title={t('error.loadDetail')} closeLabel={t('topbar.backToWorlds')}>
      <div style={{
        display: 'flex', flex: 1,
        minHeight: 0, overflow: 'hidden',
      }}>

        {/* ── Sidebar ── */}
        <nav
          aria-label={t('worldnav.agents')}
          style={{
            width: `${SIDEBAR_W}px`, flexShrink: 0,
            background: 'var(--surface)',
            borderInlineEnd: '1px solid var(--border)',
            display: 'flex', flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          <div style={{
            flex: 1, padding: '12px 8px',
            display: 'flex', flexDirection: 'column', gap: '2px',
          }}>
            {navItems.map(item => {
              const isActive = activeTab === item.id
              return (
                <button
                  key={item.id}
                  type="button"
                  disabled={item.disabled}
                  onClick={() => { if (!item.disabled) { setActiveTab(item.id); setSchedulerDashboard(null) } }}
                  aria-current={isActive ? 'page' : undefined}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '10px',
                    padding: '8px 10px',
                    borderRadius: 'var(--radius-sm)',
                    cursor: item.disabled ? 'not-allowed' : 'pointer',
                    border: 'none',
                    background: isActive ? 'var(--accent-subtle)' : 'transparent',
                    color: item.disabled
                      ? 'var(--text-disabled)'
                      : isActive
                        ? 'var(--accent-text)'
                        : 'var(--text)',
                    fontFamily: 'inherit', fontSize: '14px',
                    textAlign: 'start', width: '100%',
                    position: 'relative',
                    fontWeight: isActive ? 500 : 400,
                    transition: 'background var(--dur-fast) var(--ease)',
                  }}
                  className={item.disabled ? '' : (!isActive ? 'hover:bg-[var(--surface-2)]' : '')}
                >
                  {/* Barra de acento izquierda */}
                  {isActive && (
                    <span
                      aria-hidden="true"
                      style={{
                        position: 'absolute',
                        insetBlock: '4px',
                        insetInlineStart: 0,
                        width: '3px',
                        borderRadius: 'var(--radius-full)',
                        background: 'var(--accent)',
                      }}
                    />
                  )}
                  {item.icon}
                  <span style={{ flex: 1 }}>{item.label}</span>
                  {item.soon && (
                    <span style={{
                      fontSize: '10px',
                      color: 'var(--text-disabled)',
                      fontFamily: 'var(--font-mono)',
                      textTransform: 'uppercase',
                      letterSpacing: '.04em',
                    }}>
                      {t('worldnav.soon')}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </nav>

        {/* ── Contenido de pestaña ── */}
        <main style={{
          flex: 1, minWidth: 0,
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <div style={{
            flex: 1, overflowY: 'auto',
            padding: '24px 24px 72px', // 72px para la barra fija
          }}>

            {/* Pestaña: Agentes (con posible drill-down al SchedulerDashboard) */}
            {activeTab === 'agents' && (
              schedulerDashboard ? (
                <SchedulerDashboard
                  scheduler={schedulerDashboard}
                  schedulers={schedulers}
                  farmLists={farmLists}
                  worldId={worldId}
                  onBack={() => setSchedulerDashboard(null)}
                />
              ) : (
                <AgentsTab
                  worldId={worldId}
                  agentState={agentState}
                  agentStatus={agentStatus}
                  onAgentStart={handleAgentStart}
                  onAgentStop={handleAgentStop}
                  schedulers={schedulers}
                  loadingSchedulers={loadingSchedulers}
                  farmLists={farmLists}
                  onSchedulersChange={handleSchedulersChange}
                  onNavigateToFarmList={handleNavigateToFarmList}
                  onOpenSchedulerDashboard={(sched) => setSchedulerDashboard(sched)}
                />
              )
            )}

            {/* Pestaña: Listas de vacas */}
            {activeTab === 'farmlists' && (
              <FarmListsTab
                worldId={worldId}
                farmLists={farmLists}
                loading={loadingFarmLists}
                onSyncNow={handleSyncNow}
                syncing={syncing}
                lastSyncTime={lastSyncTime}
                schedulers={schedulers}
                onOpenDrawer={(fl) => openDrawer(fl, null)}
                highlightId={highlightFarmListId}
                onClearHighlight={() => setHighlightFarmListId(null)}
              />
            )}

            {/* Pestaña: Sesión (Human Sessions) */}
            {activeTab === 'session' && (
              <ErrorBoundary onReset={() => setActiveTab('agents')} title={t('error.loadDetail')} closeLabel={t('topbar.backToWorlds')}>
                <SessionTab worldId={worldId} />
              </ErrorBoundary>
            )}

            {/* Pestaña: Ruido (Noise catalog) */}
            {activeTab === 'noise' && (
              <ErrorBoundary onReset={() => setActiveTab('agents')} title={t('error.loadDetail')} closeLabel={t('topbar.backToWorlds')}>
                <NoiseTab worldId={worldId} />
              </ErrorBoundary>
            )}

            {/* Pestaña: Dashboard (próximamente) */}
            {activeTab === 'dashboard' && (
              <div style={{
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                padding: '64px 24px', textAlign: 'center', gap: '8px',
              }}>
                <p style={{ fontSize: '17px', fontWeight: 600 }}>
                  {t('world.config.comingSoonTitle')}
                </p>
                <p style={{ fontSize: '14px', color: 'var(--text-secondary)', maxWidth: '280px' }}>
                  {t('world.comingSoon.resourcesDesc')}
                </p>
              </div>
            )}

            {/* Pestaña: Calculadora (próximamente) */}
            {activeTab === 'calc' && (
              <div style={{
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                padding: '64px 24px', textAlign: 'center', gap: '8px',
              }}>
                <p style={{ fontSize: '17px', fontWeight: 600 }}>
                  {t('world.config.comingSoonTitle')}
                </p>
              </div>
            )}

          </div>
        </main>
      </div>

      {/* ── AgentBottomBar (fija) ── */}
      <AgentBottomBar
        agentState={agentState}
        tasks={bottomBarTasks}
        onToggle={handleToggleAgent}
      />

      {/* ── FarmListDrawer (V5/V6) ── */}
      <ErrorBoundary onReset={closeDrawer} title={t('error.loadDetail')} closeLabel={t('modal.edit.closeBtn')}>
        <FarmListDrawer
          open={drawerOpen}
          farmList={drawerFarmList}
          worldId={worldId}
          schedulerName={drawerFarmList ? getSchedulerName(drawerFarmList.scheduler_id) : null}
          worldServer={worldInfo?.server ?? null}
          tribe={worldInfo?.tribe ?? null}
          onClose={closeDrawer}
          triggerRef={drawerTriggerRef}
        />
      </ErrorBoundary>

      </ErrorBoundary>

    </div>
  )
}
