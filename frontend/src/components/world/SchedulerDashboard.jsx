/**
 * SchedulerDashboard — Vista dedicada v10 del scheduler (drill-down dentro de Agentes).
 *
 * Anidada dentro de AgentsTab cuando el usuario pulsa "Dashboard completo →".
 * El sidebar sigue mostrando "Agentes" como activo.
 *
 * Contiene:
 *  - Breadcrumb "Agentes › Dashboard {nombre}" con link ← volver
 *  - Pills selector de scheduler
 *  - 3 KPIs (siguiente envío, envíos hoy, botín medio)
 *  - Dos columnas:
 *    - Izquierda: tabla "Resumen por lista" + historial de envíos
 *    - Derecha: panel de alertas
 *
 * Props:
 *  - scheduler     {object}   scheduler inicial seleccionado
 *  - schedulers    {Array}    todos los schedulers (para pills selector)
 *  - farmLists     {Array}    todas las listas del mundo
 *  - worldId       {number}
 *  - onBack        {Function} callback para volver a la lista de schedulers
 *
 * Spec: docs/design/farm-lists-feedback.md (vista v10)
 * Playground: frontend/mockups/farm-lists-feedback.playground.html
 */
import { useState, useEffect, useCallback } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api } from '../../api/client.js'
import { showToast } from '../ui/uiUtils.jsx'
import { Countdown } from './Countdown.jsx'

// AlertsPanelDash se define localmente más abajo (AlertsPanel de SchedulerSubPanel
// es un componente interno no exportado; este dashboard tiene su propia versión ligera).

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtNum(n) {
  if (n == null || n === 0) return '—'
  return new Intl.NumberFormat('es').format(Math.round(n))
}

function fmtTime(isoString) {
  if (!isoString) return '—'
  const d = new Date(isoString)
  if (isNaN(d.getTime())) return '—'
  return (
    String(d.getHours()).padStart(2, '0') + ':' +
    String(d.getMinutes()).padStart(2, '0')
  )
}

function startOfTodayISO() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d.toISOString()
}

// ── KpiCard — tarjeta de KPI del dashboard ───────────────────────────────────

function KpiCard({ value, label, sub, variant }) {
  const valueColor = variant === 'danger' && value > 0
    ? 'var(--danger)'
    : 'var(--text)'

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      padding: '20px',
      boxShadow: 'var(--shadow-sm)',
      minWidth: 0,
      flex: 1,
    }}>
      <dl>
        <dd style={{
          fontSize: '28px', fontWeight: 600,
          fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
          lineHeight: 1.1, color: valueColor,
        }}>
          {value}
        </dd>
        {sub && (
          <dd style={{ fontSize: '12px', color: 'var(--success)', marginTop: '2px', fontFamily: 'var(--font-mono)' }}>
            {sub}
          </dd>
        )}
        <dt style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          {label}
        </dt>
      </dl>
    </div>
  )
}

// ── StatusBadge ───────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const map = {
    success: { bg: 'rgba(36,138,61,.12)', color: 'var(--success)', text: '✓ OK' },
    partial: { bg: 'var(--accent-subtle)', color: 'var(--accent-text)', text: '⚠ Parcial' },
    error:   { bg: 'rgba(201,53,44,.10)', color: 'var(--danger)', text: '✗ Error' },
  }
  const s = map[status] ?? { bg: 'var(--surface-2)', color: 'var(--text-secondary)', text: '— Desconocido' }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      borderRadius: 'var(--radius-full)', padding: '1px 6px',
      fontSize: '11px', fontWeight: 500,
      background: s.bg, color: s.color,
    }}>
      {s.text}
    </span>
  )
}

// ── AlertsPanelDash — versión local simplificada del panel de alertas ─────────

function AlertsPanelDash({ events, t }) {
  const [expanded, setExpanded] = useState(false)
  const [readAt, setReadAt] = useState(null)

  const unreadCount = readAt == null
    ? events.length
    : events.filter(e => e.timestamp && new Date(e.timestamp) > readAt).length

  function handleToggle() {
    if (!expanded) setReadAt(new Date())
    setExpanded(v => !v)
  }

  const eventIcon = (type) => type === 'LOSSES_DETECTED' ? '⚠'
    : type === 'PROBE_SENT' ? '⚡'
    : type === 'REACTIVATED' ? '✓'
    : type === 'PROBE_CANCELLED' ? '✗' : '•'

  const iconColor = (type) => type === 'LOSSES_DETECTED' ? 'var(--accent)'
    : type === 'PROBE_SENT' ? 'var(--text-secondary)'
    : type === 'REACTIVATED' ? 'var(--success)'
    : 'var(--text-tertiary)'

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      overflow: 'hidden',
    }}>
      <button
        type="button"
        aria-expanded={expanded}
        onClick={handleToggle}
        style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          padding: '12px 16px', width: '100%', textAlign: 'start',
          border: 'none', background: 'transparent', cursor: 'pointer', fontFamily: 'inherit',
          borderBottom: expanded ? '1px solid var(--border)' : 'none',
          transition: 'background var(--dur-fast)',
        }}
        className="hover:bg-[var(--surface-2)]"
      >
        <span style={{ fontSize: '13px', fontWeight: 600, flex: 1 }}>
          {t('schedulerDash.alerts.title')}
        </span>
        {unreadCount > 0 && (
          <span aria-hidden="true" style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            minWidth: '17px', height: '17px', padding: '0 4px',
            borderRadius: 'var(--radius-full)',
            background: 'var(--danger)', color: '#fff',
            fontSize: '10px', fontWeight: 700, lineHeight: 1,
          }}>{unreadCount}</span>
        )}
        <span aria-hidden="true" style={{
          fontSize: '10px', color: 'var(--text-tertiary)',
          transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
          transition: 'transform var(--dur-fast)',
        }}>▼</span>
      </button>

      {expanded && (
        <div>
          {events.length === 0 ? (
            <p style={{ padding: '16px', fontSize: '12px', color: 'var(--text-tertiary)', textAlign: 'center' }}>
              {t('scheduler.subpanel.alerts.empty')}
            </p>
          ) : events.map((ev, i) => {
            const ms = ev.timestamp ? Date.now() - new Date(ev.timestamp).getTime() : 0
            const secsAgo = Math.floor(ms / 1000)
            const agoText = secsAgo < 60 ? `hace ${secsAgo}s`
              : secsAgo < 3600 ? `hace ${Math.floor(secsAgo / 60)} min`
              : `hace ${Math.floor(secsAgo / 3600)} h`

            let alertText = ev.slot_name ?? '—'
            if (ev.event_type === 'LOSSES_DETECTED') alertText = `${ev.slot_name} · Pérdidas detectadas`
            else if (ev.event_type === 'PROBE_SENT') alertText = `${ev.farm_list_name} · Sonda enviada a ${ev.slot_name}`
            else if (ev.event_type === 'REACTIVATED') alertText = `${ev.slot_name} · Reactivado`
            else if (ev.event_type === 'PROBE_CANCELLED') alertText = `${ev.slot_name} · Sonda cancelada`

            return (
              <div key={ev.id ?? i} style={{
                display: 'flex', alignItems: 'flex-start', gap: '10px',
                padding: '10px 16px', borderBottom: '1px solid var(--border)',
              }}>
                <span style={{ fontSize: '13px', color: iconColor(ev.event_type), flexShrink: 0, marginTop: '1px' }}
                  aria-hidden="true">{eventIcon(ev.event_type)}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '12px' }}>{alertText}</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>{agoText}</div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── SchedulerDashboard ────────────────────────────────────────────────────────

export function SchedulerDashboard({ scheduler: initialScheduler, schedulers, farmLists, worldId, onBack }) {
  const { t } = useI18n()
  const [activeScheduler, setActiveScheduler] = useState(initialScheduler)
  const [historyItems, setHistoryItems] = useState([])
  const [alertEvents, setAlertEvents] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    if (!activeScheduler) return
    try {
      const [histRes, eventsRes] = await Promise.all([
        api.getWorldHistory(worldId, {
          schedulerId: activeScheduler.id,
          page: 1,
          pageSize: 50,
        }),
        api.getSlotEvents(worldId, { page: 1, pageSize: 20 }),
      ])
      setHistoryItems(histRes?.items ?? [])
      const schedListIds = new Set(activeScheduler.farm_list_ids ?? [])
      setAlertEvents((eventsRes?.items ?? []).filter(e =>
        !schedListIds.size || schedListIds.has(e.farm_list_id)
      ))
    } catch {
      showToast(t('error.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [worldId, activeScheduler?.id])

  useEffect(() => {
    setLoading(true)
    fetchData()
  }, [fetchData])

  // KPIs calculados
  const sendsToday = historyItems.filter(e => {
    if (!e.timestamp) return false
    return new Date(e.timestamp) >= new Date(startOfTodayISO())
  }).length

  const avgBounty = (() => {
    const items = historyItems.filter(e => e.status === 'success' || e.status === 'partial')
    if (!items.length) return null
    const total = items.reduce((s, e) => s + (e.loot_wood ?? 0) + (e.loot_clay ?? 0) + (e.loot_iron ?? 0) + (e.loot_crop ?? 0), 0)
    return Math.round(total / items.length)
  })()

  // Resumen por lista: agrupar historial por farm_list_id
  const listsSummary = (activeScheduler?.farm_list_ids ?? []).map(flId => {
    const fl = farmLists?.find(f => f.id === flId)
    const listEvents = historyItems.filter(e => e.farm_list_id === flId)
    const lastEvent = listEvents[0] ?? null
    const activeSlots = fl?.slots?.filter(s => s.is_active).length ?? 0
    const totalSlots = fl?.slots?.length ?? 0
    const avgB = (() => {
      const valid = listEvents.filter(e => e.status !== 'error')
      if (!valid.length) return 0
      const total = valid.reduce((s, e) => s + (e.loot_wood ?? 0) + (e.loot_clay ?? 0) + (e.loot_iron ?? 0) + (e.loot_crop ?? 0), 0)
      return Math.round(total / valid.length)
    })()
    return {
      id: flId,
      name: fl?.name ?? `#${flId}`,
      lastStatus: lastEvent?.status ?? null,
      sentSlots: lastEvent?.being_raided_current ?? 0,
      activeSlots,
      totalSlots,
      avgBounty: avgB,
      lastTime: lastEvent?.timestamp ?? null,
    }
  })

  return (
    <div>
      {/* Breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
        <button
          type="button"
          onClick={onBack}
          style={{
            appearance: 'none', border: 'none', background: 'transparent',
            color: 'var(--accent-text)', fontSize: '13px', cursor: 'pointer',
            fontFamily: 'inherit', padding: 0,
          }}
          onMouseEnter={e => { e.currentTarget.style.textDecoration = 'underline' }}
          onMouseLeave={e => { e.currentTarget.style.textDecoration = 'none' }}
        >
          {t('schedulerDash.breadcrumb.back')}
        </button>
        <span style={{ color: 'var(--text-disabled)' }}>›</span>
        <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
          {t('schedulerDash.breadcrumb.agents')}
        </span>
        <span style={{ color: 'var(--text-disabled)' }}>›</span>
        <span style={{ fontSize: '13px', fontWeight: 500 }}>
          {t('schedulerDash.title').replace('{name}', activeScheduler?.name ?? '')}
        </span>
      </div>

      {/* Pills selector de scheduler */}
      {schedulers.length > 1 && (
        <div style={{
          display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '20px',
        }}>
          {schedulers.map(sch => (
            <button
              key={sch.id}
              type="button"
              onClick={() => { setActiveScheduler(sch); setLoading(true) }}
              style={{
                appearance: 'none',
                border: `1px solid ${activeScheduler?.id === sch.id ? 'var(--accent)' : 'var(--border)'}`,
                background: activeScheduler?.id === sch.id ? 'var(--accent-subtle)' : 'var(--surface)',
                color: activeScheduler?.id === sch.id ? 'var(--accent-text)' : 'var(--text)',
                padding: '4px 12px', borderRadius: 'var(--radius-full)',
                fontSize: '12px', cursor: 'pointer', fontFamily: 'inherit',
                fontWeight: activeScheduler?.id === sch.id ? 500 : 400,
                transition: 'background var(--dur-fast), border-color var(--dur-fast)',
              }}
            >
              {sch.name}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <DashboardSkeleton />
      ) : (
        <>
          {/* KPIs */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3,1fr)',
            gap: '16px', marginBottom: '24px',
          }}
            className="max-sm:grid-cols-1"
          >
            <KpiCard
              value={
                activeScheduler?.next_run
                  ? <Countdown targetIso={activeScheduler.next_run} />
                  : '—'
              }
              label={t('schedulerDash.kpi.nextSend')}
            />
            <KpiCard
              value={sendsToday}
              label={t('schedulerDash.kpi.sendsToday')}
            />
            <KpiCard
              value={avgBounty != null ? fmtNum(avgBounty) : '—'}
              label={t('schedulerDash.kpi.avgBounty')}
            />
          </div>

          {/* Dos columnas: izq. tablas / der. alertas */}
          <div style={{ display: 'flex', gap: '24px', alignItems: 'flex-start' }}
            className="max-md:flex-col"
          >
            {/* Columna izquierda — tablas */}
            <div style={{ flex: 2, minWidth: 0 }}>

              {/* Tabla: Resumen por lista */}
              <div style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                overflow: 'hidden',
                marginBottom: '20px',
                boxShadow: 'var(--shadow-sm)',
              }}>
                <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
                  <span style={{ fontSize: '13px', fontWeight: 600 }}>
                    {t('schedulerDash.table.title')}
                  </span>
                </div>
                {listsSummary.length === 0 ? (
                  <p style={{ padding: '24px', fontSize: '13px', color: 'var(--text-secondary)', textAlign: 'center' }}>
                    {t('schedulerDash.table.empty')}
                  </p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr>
                          {[
                            t('schedulerDash.table.col.list'),
                            t('schedulerDash.table.col.status'),
                            t('schedulerDash.table.col.sent'),
                            t('schedulerDash.table.col.active'),
                            t('schedulerDash.table.col.avgBounty'),
                            t('schedulerDash.table.col.lastSend'),
                          ].map(h => (
                            <th key={h} scope="col" style={{
                              fontSize: '11px', color: 'var(--text-secondary)',
                              textTransform: 'uppercase', letterSpacing: '.04em',
                              fontWeight: 500, padding: '8px 12px',
                              borderBottom: '1px solid var(--border)',
                              textAlign: 'start', whiteSpace: 'nowrap',
                            }}>
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {listsSummary.map(ls => (
                          <tr key={ls.id}
                            style={{ borderBottom: '1px solid var(--border)' }}>
                            <td style={{ padding: '9px 12px', fontSize: '13px', fontWeight: 500 }}>
                              {ls.name}
                            </td>
                            <td style={{ padding: '9px 12px' }}>
                              {ls.lastStatus ? <StatusBadge status={ls.lastStatus} /> : <span style={{ color: 'var(--text-disabled)', fontSize: '12px' }}>—</span>}
                            </td>
                            <td style={{
                              padding: '9px 12px',
                              fontFamily: 'var(--font-mono)', fontSize: '12px',
                              fontVariantNumeric: 'tabular-nums',
                            }}>
                              {ls.sentSlots || '—'}
                            </td>
                            <td style={{
                              padding: '9px 12px',
                              fontFamily: 'var(--font-mono)', fontSize: '12px',
                              fontVariantNumeric: 'tabular-nums',
                            }}>
                              {ls.totalSlots > 0 ? `${ls.activeSlots}/${ls.totalSlots}` : '—'}
                            </td>
                            <td style={{
                              padding: '9px 12px',
                              fontFamily: 'var(--font-mono)', fontSize: '12px',
                              fontVariantNumeric: 'tabular-nums',
                              color: 'var(--accent-text)',
                            }}>
                              {ls.avgBounty > 0 ? fmtNum(ls.avgBounty) : '—'}
                            </td>
                            <td style={{
                              padding: '9px 12px',
                              fontFamily: 'var(--font-mono)', fontSize: '12px',
                              color: 'var(--text-tertiary)',
                              whiteSpace: 'nowrap',
                            }}>
                              {fmtTime(ls.lastTime)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Historial de envíos cross-lista */}
              <div style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                overflow: 'hidden',
                boxShadow: 'var(--shadow-sm)',
              }}>
                <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
                  <span style={{ fontSize: '13px', fontWeight: 600 }}>
                    {t('schedulerDash.history.title')}
                  </span>
                </div>
                {historyItems.length === 0 ? (
                  <p style={{ padding: '24px', fontSize: '13px', color: 'var(--text-secondary)', textAlign: 'center' }}>
                    {t('history.empty')}
                  </p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr>
                          {[t('history.col.time'), 'Lista', t('history.col.status'), t('history.col.slots'), t('history.col.origin')].map(h => (
                            <th key={h} scope="col" style={{
                              fontSize: '11px', color: 'var(--text-secondary)',
                              textTransform: 'uppercase', letterSpacing: '.04em',
                              fontWeight: 500, padding: '8px 12px',
                              borderBottom: '1px solid var(--border)',
                              textAlign: 'start', whiteSpace: 'nowrap',
                            }}>
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {historyItems.slice(0, 20).map((ev, i) => (
                          <tr key={ev.id ?? i} style={{ borderBottom: '1px solid var(--border)' }}>
                            <td style={{
                              padding: '8px 12px',
                              fontFamily: 'var(--font-mono)', fontSize: '12px',
                              fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap',
                            }}>
                              {fmtTime(ev.timestamp)}
                            </td>
                            <td style={{ padding: '8px 12px', fontSize: '12px' }}>
                              {ev.farm_list_name ?? `#${ev.farm_list_id}`}
                            </td>
                            <td style={{ padding: '8px 12px' }}>
                              <StatusBadge status={ev.status} />
                            </td>
                            <td style={{
                              padding: '8px 12px',
                              fontFamily: 'var(--font-mono)', fontSize: '12px',
                              fontVariantNumeric: 'tabular-nums',
                            }}>
                              {ev.being_raided_current ?? '—'}
                            </td>
                            <td style={{
                              padding: '8px 12px',
                              fontSize: '11px', color: 'var(--text-secondary)',
                            }}>
                              {ev.triggered_by === 'scheduler' ? t('history.triggered.scheduler') : t('history.triggered.manual')}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>

            {/* Columna derecha — alertas */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <AlertsPanelDash events={alertEvents} t={t} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ── DashboardSkeleton ─────────────────────────────────────────────────────────

function DashboardSkeleton() {
  const pulse = {
    background: 'var(--surface-2)',
    borderRadius: '4px',
    animation: 'pulse 1.2s ease-in-out infinite',
  }
  return (
    <div aria-hidden="true">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: '16px', marginBottom: '24px' }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{ ...pulse, height: '90px', borderRadius: 'var(--radius-md)' }} />
        ))}
      </div>
      <div style={{ display: 'flex', gap: '24px' }}>
        <div style={{ flex: 2 }}>
          <div style={{ ...pulse, height: '200px', borderRadius: 'var(--radius-md)', marginBottom: '20px' }} />
          <div style={{ ...pulse, height: '160px', borderRadius: 'var(--radius-md)' }} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ ...pulse, height: '200px', borderRadius: 'var(--radius-md)' }} />
        </div>
      </div>
    </div>
  )
}
