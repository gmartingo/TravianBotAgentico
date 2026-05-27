/**
 * SchedulerSubPanel — Sub-panel operativo que aparece al expandir un scheduler card.
 *
 * Contiene:
 *  - Enlace "Dashboard completo →" (navega a la vista v10 del scheduler)
 *  - 3 KPIs: siguiente envío (countdown) + envíos hoy + botín medio
 *  - Feed de actividad reciente del scheduler (polling 10s)
 *  - Panel de alertas colapsable con contador de no-leídas
 *
 * Props:
 *  - scheduler       {object}   scheduler completo
 *  - worldId         {number}
 *  - farmLists       {Array}    listas del mundo (para resolver nombres)
 *  - onOpenDashboard {Function} callback para abrir el dashboard dedicado (v10)
 *  - t               {Function} función de i18n
 *
 * Spec: docs/design/farm-lists-feedback.md (vistas v2, v3, v4)
 * Playground: frontend/mockups/farm-lists-feedback.playground.html
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../../api/client.js'
import { showToast } from '../ui/uiUtils.jsx'
import { Countdown } from './Countdown.jsx'

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

function elapsedText(sinceMs) {
  const secs = Math.floor(sinceMs / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins} min`
  return `${Math.floor(mins / 60)} h`
}

// ── ElapsedTimer — "Actualizado hace Xs" ────────────────────────────────────

function ElapsedTimer({ sinceMs, tpl }) {
  const [elapsed, setElapsed] = useState(sinceMs)

  useEffect(() => {
    setElapsed(sinceMs)
    const id = setInterval(() => setElapsed(prev => prev + 1000), 1000)
    return () => clearInterval(id)
  }, [sinceMs])

  return (
    <span
      aria-live="off"
      style={{
        fontSize: '11px',
        color: 'var(--text-tertiary)',
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      {tpl.replace('{t}', elapsedText(elapsed))}
    </span>
  )
}

// ── KpiMini — tarjeta KPI compacta del sub-panel ─────────────────────────────

function KpiMini({ value, label, sub, variant }) {
  const valueColor = variant === 'danger' && value > 0
    ? 'var(--danger)'
    : 'var(--text)'

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      padding: '14px 16px',
      minWidth: 0,
      flex: 1,
    }}>
      <dl>
        <dd style={{
          fontSize: '22px',
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
          fontVariantNumeric: 'tabular-nums',
          lineHeight: 1.1,
          color: valueColor,
        }}>
          {value}
        </dd>
        {sub && (
          <dd style={{
            fontSize: '11px',
            color: 'var(--success)',
            fontFamily: 'var(--font-mono)',
            marginTop: '2px',
          }}>
            {sub}
          </dd>
        )}
        <dt style={{
          fontSize: '11px',
          color: 'var(--text-secondary)',
          marginTop: '4px',
          textTransform: 'uppercase',
          letterSpacing: '.04em',
        }}>
          {label}
        </dt>
      </dl>
    </div>
  )
}

// ── FeedRow — fila del feed de actividad ──────────────────────────────────────

function FeedRow({ event, isNew, farmLists }) {
  const [highlighted, setHighlighted] = useState(isNew)

  useEffect(() => {
    if (!isNew) return
    setHighlighted(true)
    const id = setTimeout(() => setHighlighted(false), 2500)
    return () => clearTimeout(id)
  }, [isNew])

  const statusIcon = event.status === 'success' ? '✓'
    : event.status === 'partial' ? '⚠'
    : event.status === 'error' ? '✗' : '?'

  const statusColor = event.status === 'success' ? 'var(--success)'
    : event.status === 'partial' ? 'var(--accent)'
    : event.status === 'error' ? 'var(--danger)' : 'var(--text-tertiary)'

  const listName = event.farm_list_name
    || farmLists?.find(f => f.id === event.farm_list_id)?.name
    || `#${event.farm_list_id}`

  const origin = event.triggered_by === 'scheduler' ? 'Auto' : 'Manual'

  return (
    <tr
      aria-label={isNew ? `Nuevo envío: ${listName} a las ${fmtTime(event.timestamp)}` : undefined}
      style={{
        borderBottom: '1px solid var(--border)',
        background: highlighted ? 'var(--accent-subtle)' : 'transparent',
        transition: 'background 1s var(--ease)',
      }}
    >
      <td style={{ padding: '8px 10px 8px 14px', verticalAlign: 'middle' }}>
        <span style={{ color: statusColor, fontWeight: 600, fontSize: '13px' }}>
          {statusIcon}
        </span>
      </td>
      <td style={{ padding: '8px 6px', verticalAlign: 'middle', fontSize: '13px', fontWeight: 500 }}>
        {listName}
      </td>
      <td style={{
        padding: '8px 6px', verticalAlign: 'middle',
        fontFamily: 'var(--font-mono)', fontSize: '12px',
        color: 'var(--text-tertiary)', whiteSpace: 'nowrap',
      }}>
        {fmtTime(event.timestamp)}
      </td>
      <td style={{
        padding: '8px 6px', verticalAlign: 'middle',
        fontFamily: 'var(--font-mono)', fontSize: '12px',
        fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap',
      }}>
        {event.being_raided_current != null
          ? `${event.being_raided_current}/${event.being_raided_total ?? '?'}`
          : '—'
        }
      </td>
      <td style={{
        padding: '8px 14px 8px 6px', verticalAlign: 'middle',
        fontSize: '12px', color: 'var(--text-secondary)', whiteSpace: 'nowrap',
      }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          {origin}
          {isNew && (
            <span style={{
              display: 'inline-flex', alignItems: 'center',
              background: 'var(--accent-subtle)',
              color: 'var(--accent-text)',
              fontSize: '10px', fontWeight: 700,
              padding: '1px 6px',
              borderRadius: 'var(--radius-full)',
              textTransform: 'uppercase', letterSpacing: '.04em',
            }}>
              NEW
            </span>
          )}
        </span>
      </td>
    </tr>
  )
}

// ── AlertRow — fila de alerta de slot ────────────────────────────────────────

function AlertRow({ event, onProbeAction, t }) {
  const [confirmMode, setConfirmMode] = useState(null) // null | 'activate' | 'cancel'
  const [acting, setActing] = useState(false)

  const eventIcon = event.event_type === 'LOSSES_DETECTED' ? '⚠'
    : event.event_type === 'PROBE_SENT' ? '⚡'
    : event.event_type === 'REACTIVATED' ? '✓'
    : event.event_type === 'PROBE_CANCELLED' ? '✗' : '•'

  const iconColor = event.event_type === 'LOSSES_DETECTED' ? 'var(--accent)'
    : event.event_type === 'PROBE_SENT' ? 'var(--text-secondary)'
    : event.event_type === 'REACTIVATED' ? 'var(--success)'
    : 'var(--text-tertiary)'

  // Construir texto de alerta usando clave i18n
  let alertText = event.slot_name ?? '—'
  if (event.event_type === 'LOSSES_DETECTED') {
    alertText = t('alertEvent.LOSSES_DETECTED').replace('{slot}', event.slot_name ?? '—')
  } else if (event.event_type === 'PROBE_SENT') {
    alertText = t('alertEvent.PROBE_SENT')
      .replace('{list}', event.farm_list_name ?? '—')
      .replace('{slot}', event.slot_name ?? '—')
  } else if (event.event_type === 'REACTIVATED') {
    alertText = t('alertEvent.REACTIVATED').replace('{slot}', event.slot_name ?? '—')
  } else if (event.event_type === 'PROBE_CANCELLED') {
    alertText = t('alertEvent.PROBE_CANCELLED').replace('{slot}', event.slot_name ?? '—')
  }

  // Calcular tiempo relativo
  const ms = event.timestamp ? Date.now() - new Date(event.timestamp).getTime() : 0
  const secsAgo = Math.floor(ms / 1000)
  let agoText
  if (secsAgo < 60) agoText = `hace ${secsAgo}s`
  else if (secsAgo < 3600) agoText = `hace ${Math.floor(secsAgo / 60)} min`
  else agoText = `hace ${Math.floor(secsAgo / 3600)} h`

  async function handleConfirm() {
    if (!confirmMode || acting) return
    setActing(true)
    try {
      await onProbeAction(event, confirmMode)
      setConfirmMode(null)
    } catch {
      showToast(t('slot.error.actionFailed'))
    } finally {
      setActing(false)
    }
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: '10px',
      padding: '10px 14px',
      borderBottom: '1px solid var(--border)',
    }}>
      {/* Icono */}
      <span style={{ fontSize: '13px', color: iconColor, flexShrink: 0, marginTop: '1px' }}
        aria-hidden="true">
        {eventIcon}
      </span>
      {/* Contenido */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '12px', color: 'var(--text)' }}>{alertText}</div>
        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
          {agoText}
        </div>
        {/* Acciones inline */}
        {event.event_type === 'LOSSES_DETECTED' && !confirmMode && (
          <div style={{ marginTop: '5px', display: 'flex', gap: '6px' }}>
            <button
              type="button"
              onClick={() => setConfirmMode('activate')}
              style={{
                appearance: 'none',
                border: '1px solid var(--border)',
                background: 'var(--surface)',
                color: 'var(--text-secondary)',
                fontSize: '11px', padding: '3px 9px',
                borderRadius: 'var(--radius-full)',
                cursor: 'pointer', fontFamily: 'inherit',
              }}
            >
              {t('alertEvent.probe.activate')}
            </button>
          </div>
        )}
        {event.event_type === 'PROBE_SENT' && !confirmMode && (
          <div style={{ marginTop: '5px', display: 'flex', gap: '6px' }}>
            <button
              type="button"
              onClick={() => setConfirmMode('cancel')}
              style={{
                appearance: 'none',
                border: '1px solid var(--border)',
                background: 'var(--surface)',
                color: 'var(--danger)',
                fontSize: '11px', padding: '3px 9px',
                borderRadius: 'var(--radius-full)',
                cursor: 'pointer', fontFamily: 'inherit',
              }}
            >
              {t('alertEvent.probe.cancel')}
            </button>
          </div>
        )}
        {/* Panel de confirmación inline (NO modal) */}
        {confirmMode && (
          <div style={{
            marginTop: '8px',
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '8px 10px',
          }}>
            <p style={{ fontSize: '12px', marginBottom: '8px', color: 'var(--text)' }}>
              {confirmMode === 'activate'
                ? t('scheduler.subpanel.probe.confirm.activate')
                : t('scheduler.subpanel.probe.confirm.cancel')
              }
            </p>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                type="button"
                disabled={acting}
                onClick={handleConfirm}
                style={{
                  appearance: 'none',
                  border: 'none',
                  background: 'var(--btn-primary-bg)',
                  color: 'var(--btn-primary-text)',
                  fontSize: '11px', padding: '4px 10px',
                  borderRadius: 'var(--radius-sm)',
                  cursor: acting ? 'not-allowed' : 'pointer',
                  fontFamily: 'inherit',
                  opacity: acting ? 0.6 : 1,
                }}
              >
                {t('scheduler.subpanel.probe.btn.confirm')}
              </button>
              <button
                type="button"
                disabled={acting}
                onClick={() => setConfirmMode(null)}
                style={{
                  appearance: 'none',
                  border: '1px solid var(--border)',
                  background: 'var(--surface)',
                  color: 'var(--text)',
                  fontSize: '11px', padding: '4px 10px',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                {t('scheduler.subpanel.probe.btn.dismiss')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── AlertsPanel — panel colapsable de alertas ─────────────────────────────────

function AlertsPanel({ events, onProbeAction, t }) {
  const [expanded, setExpanded] = useState(false)
  // Contar eventos sin leer: los que llegaron antes del expand
  const [readAt, setReadAt] = useState(null)

  const unreadCount = readAt == null
    ? events.length
    : events.filter(e => e.timestamp && new Date(e.timestamp) > readAt).length

  function handleToggle() {
    if (!expanded) {
      setReadAt(new Date())
    }
    setExpanded(v => !v)
  }

  const ariaLabel = unreadCount > 0
    ? `${t('scheduler.subpanel.alerts.title')} (${t('scheduler.subpanel.alerts.unread').replace('{n}', unreadCount)})`
    : t('scheduler.subpanel.alerts.title')

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      overflow: 'hidden',
    }}>
      {/* Header toggle */}
      <button
        type="button"
        aria-expanded={expanded}
        aria-label={ariaLabel}
        onClick={handleToggle}
        style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          padding: '10px 14px',
          width: '100%', textAlign: 'start',
          border: 'none', background: 'transparent',
          cursor: 'pointer', fontFamily: 'inherit',
          borderBottom: expanded ? '1px solid var(--border)' : 'none',
          transition: 'background var(--dur-fast)',
        }}
        className="hover:bg-[var(--surface-2)]"
      >
        <span style={{ fontSize: '12px', fontWeight: 600, flex: 1 }}>
          {t('scheduler.subpanel.alerts.title')}
        </span>
        {unreadCount > 0 && (
          <span
            aria-hidden="true"
            style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              minWidth: '17px', height: '17px', padding: '0 4px',
              borderRadius: 'var(--radius-full)',
              background: 'var(--danger)', color: '#fff',
              fontSize: '10px', fontWeight: 700, lineHeight: 1,
            }}
          >
            {unreadCount}
          </span>
        )}
        <span
          aria-hidden="true"
          style={{
            fontSize: '10px', color: 'var(--text-tertiary)',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform var(--dur-fast)',
          }}
        >
          ▼
        </span>
      </button>

      {/* Body — colapsado con max-height */}
      {expanded && (
        <div>
          {events.length === 0 ? (
            <p style={{
              padding: '12px 14px',
              fontSize: '12px', color: 'var(--text-tertiary)',
              textAlign: 'center',
            }}>
              {t('scheduler.subpanel.alerts.empty')}
            </p>
          ) : (
            events.map((ev, i) => (
              <AlertRow
                key={ev.id ?? i}
                event={ev}
                onProbeAction={onProbeAction}
                t={t}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ── SchedulerSubPanel (exportación principal) ─────────────────────────────────

export function SchedulerSubPanel({ scheduler, worldId, farmLists, onOpenDashboard, t }) {
  const [loading, setLoading] = useState(true)
  const [feedEvents, setFeedEvents] = useState([])
  const [alertEvents, setAlertEvents] = useState([])
  const [lastFetchMs, setLastFetchMs] = useState(0)
  const [newEventIds, setNewEventIds] = useState(new Set())
  const prevEventIdsRef = useRef(new Set())

  // Calcular KPIs del scheduler a partir del feed
  const sendsToday = feedEvents.filter(e => {
    if (!e.timestamp) return false
    return new Date(e.timestamp) >= new Date(startOfTodayISO())
  }).length

  const avgBounty = (() => {
    const successEvents = feedEvents.filter(e => e.status === 'success' || e.status === 'partial')
    if (!successEvents.length) return null
    const totalBounty = successEvents.reduce((sum, e) => {
      const loot = (e.loot_wood ?? 0) + (e.loot_clay ?? 0) + (e.loot_iron ?? 0) + (e.loot_crop ?? 0)
      return sum + loot
    }, 0)
    return Math.round(totalBounty / successEvents.length)
  })()

  const fetchData = useCallback(async () => {
    try {
      const [histRes, eventsRes] = await Promise.all([
        api.getWorldHistory(worldId, {
          schedulerId: scheduler.id,
          page: 1,
          pageSize: 10,
        }),
        api.getSlotEvents(worldId, { page: 1, pageSize: 20 }),
      ])

      const newItems = histRes?.items ?? []
      const currentIds = new Set(newItems.map(e => e.id).filter(Boolean))

      // Detectar filas nuevas comparando con la carga anterior
      const newOnes = new Set()
      if (prevEventIdsRef.current.size > 0) {
        for (const id of currentIds) {
          if (!prevEventIdsRef.current.has(id)) newOnes.add(id)
        }
      }
      prevEventIdsRef.current = currentIds

      setFeedEvents(newItems)
      if (newOnes.size > 0) {
        setNewEventIds(newOnes)
        // Limpiar el resaltado después de 3s
        setTimeout(() => setNewEventIds(new Set()), 3000)
      }

      // Filtrar alertas del scheduler actual (por farm_list_id en las listas del scheduler)
      const schedListIds = new Set(scheduler.farm_list_ids ?? [])
      const relevantAlerts = (eventsRes?.items ?? []).filter(e =>
        !schedListIds.size || schedListIds.has(e.farm_list_id)
      )
      setAlertEvents(relevantAlerts)
      setLastFetchMs(0)
    } catch {
      // Polling falla silenciosamente
    } finally {
      setLoading(false)
    }
  }, [worldId, scheduler.id, scheduler.farm_list_ids])

  // Carga inicial
  useEffect(() => {
    setLoading(true)
    fetchData()
  }, [fetchData])

  // Polling cada 10s
  useEffect(() => {
    const id = setInterval(() => {
      fetchData()
      setLastFetchMs(0)
    }, 10_000)
    return () => clearInterval(id)
  }, [fetchData])

  // Timer para "Actualizado hace Xs" — incrementa cada segundo
  useEffect(() => {
    const id = setInterval(() => setLastFetchMs(prev => prev + 1000), 1000)
    return () => clearInterval(id)
  }, [])

  async function handleProbeAction(event, mode) {
    // Los eventos de alerta no tienen slotId directo en el schema de SlotEvent
    // — notificamos pero no ejecutamos acción de browser (endpoint requiere sesión activa)
    // TODO: cuando el endpoint de sonda esté disponible, llamar api.cancelProbe / api.activateSlot
    showToast(t('scheduler.subpanel.toggle.soon'))
  }

  if (loading) return <SubPanelSkeleton />

  const displayFeed = feedEvents.slice(0, 10)

  return (
    <div style={{
      background: 'var(--surface-2)',
      border: '1px solid var(--border)',
      borderTop: 'none',
      borderRadius: '0 0 var(--radius-md) var(--radius-md)',
      padding: '16px',
    }}>
      {/* Link "Dashboard completo →" */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '12px' }}>
        <button
          type="button"
          onClick={onOpenDashboard}
          style={{
            appearance: 'none', border: 'none', background: 'transparent',
            color: 'var(--accent-text)', fontSize: '12px', cursor: 'pointer',
            fontFamily: 'inherit', padding: 0,
            transition: 'color var(--dur-fast)',
          }}
          onMouseEnter={e => { e.currentTarget.style.color = 'var(--accent-hover)'; e.currentTarget.style.textDecoration = 'underline' }}
          onMouseLeave={e => { e.currentTarget.style.color = 'var(--accent-text)'; e.currentTarget.style.textDecoration = 'none' }}
        >
          {t('scheduler.subpanel.dashboardLink')}
        </button>
      </div>

      {/* KPIs 3 columnas */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1.8fr 1fr 1.2fr',
        gap: '10px',
        marginBottom: '16px',
      }}
        className="max-sm:grid-cols-2"
      >
        {/* KPI 1: Siguiente envío */}
        <div style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '14px 16px',
        }}>
          <dl>
            <dd style={{
              fontSize: '22px', fontWeight: 600,
              fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
              lineHeight: 1.1,
            }}>
              {scheduler.next_run ? (
                <Countdown targetIso={scheduler.next_run} />
              ) : (
                <span style={{ color: 'var(--text-disabled)' }}>—</span>
              )}
            </dd>
            {scheduler.next_run && (
              <dd style={{ fontSize: '11px', color: 'var(--success)', marginTop: '2px', fontFamily: 'var(--font-mono)' }}>
                {t('scheduler.subpanel.kpi.in').replace('{t}',
                  (() => {
                    const secs = Math.max(0, Math.floor((new Date(scheduler.next_run) - Date.now()) / 1000))
                    if (secs < 60) return `${secs}s`
                    if (secs < 3600) return `${Math.floor(secs / 60)} min`
                    return `${Math.floor(secs / 3600)} h ${Math.floor((secs % 3600) / 60)} min`
                  })()
                )}
              </dd>
            )}
            <dt style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px', textTransform: 'uppercase', letterSpacing: '.04em' }}>
              {t('scheduler.subpanel.kpi.nextSend')}
            </dt>
          </dl>
        </div>

        {/* KPI 2: Envíos hoy */}
        <KpiMini
          value={sendsToday}
          label={t('scheduler.subpanel.kpi.sendsToday')}
        />

        {/* KPI 3: Botín medio */}
        <KpiMini
          value={avgBounty != null ? fmtNum(avgBounty) : '—'}
          label={t('scheduler.subpanel.kpi.avgBounty')}
        />
      </div>

      {/* Dos columnas: feed izq. / alertas der. */}
      <div style={{
        display: 'flex', gap: '16px', alignItems: 'flex-start',
      }}
        className="max-md:flex-col"
      >
        {/* Feed de actividad */}
        <div style={{ flex: 3, minWidth: 0 }}>
          <div style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            overflow: 'hidden',
          }}>
            {/* Header del feed */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '10px 14px',
              borderBottom: '1px solid var(--border)',
            }}>
              <span style={{ fontSize: '12px', fontWeight: 600, flex: 1 }}>
                {t('scheduler.subpanel.feed.title')}
              </span>
              <ElapsedTimer
                sinceMs={lastFetchMs}
                tpl={t('scheduler.subpanel.feed.updatedAgo')}
              />
            </div>

            {/* Tabla del feed */}
            {displayFeed.length === 0 ? (
              <p style={{
                padding: '16px 14px',
                fontSize: '12px', color: 'var(--text-tertiary)',
                textAlign: 'center',
              }}>
                {t('scheduler.subpanel.feed.empty')}
              </p>
            ) : (
              <div
                aria-live="polite"
                aria-label={t('scheduler.subpanel.feed.title')}
              >
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <tbody>
                    {displayFeed.map((ev, i) => (
                      <FeedRow
                        key={ev.id ?? i}
                        event={ev}
                        isNew={newEventIds.has(ev.id)}
                        farmLists={farmLists}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Footer del feed */}
            <div style={{
              padding: '8px 14px',
              borderTop: displayFeed.length > 0 ? '1px solid var(--border)' : 'none',
              display: 'flex', justifyContent: 'flex-end',
            }}>
              <button
                type="button"
                onClick={onOpenDashboard}
                style={{
                  appearance: 'none', border: 'none', background: 'transparent',
                  color: 'var(--accent-text)', fontSize: '11px', cursor: 'pointer',
                  fontFamily: 'inherit', padding: 0,
                }}
                onMouseEnter={e => { e.currentTarget.style.textDecoration = 'underline' }}
                onMouseLeave={e => { e.currentTarget.style.textDecoration = 'none' }}
              >
                {t('scheduler.subpanel.feed.viewAll')}
              </button>
            </div>
          </div>
        </div>

        {/* Panel alertas */}
        <div style={{ flex: 2, minWidth: 0 }}>
          <AlertsPanel
            events={alertEvents}
            onProbeAction={handleProbeAction}
            t={t}
          />
        </div>
      </div>
    </div>
  )
}

// ── SubPanelSkeleton ──────────────────────────────────────────────────────────

function SubPanelSkeleton() {
  const pulse = {
    background: 'var(--surface-2)',
    borderRadius: '4px',
    animation: 'pulse 1.2s ease-in-out infinite',
  }
  return (
    <div style={{
      background: 'var(--surface-2)',
      border: '1px solid var(--border)', borderTop: 'none',
      borderRadius: '0 0 var(--radius-md) var(--radius-md)',
      padding: '16px',
    }} aria-hidden="true">
      {/* KPI skeletons */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: '10px', marginBottom: '16px' }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{ ...pulse, height: '74px', borderRadius: 'var(--radius-md)' }} />
        ))}
      </div>
      {/* Feed + alertas skeletons */}
      <div style={{ display: 'flex', gap: '16px' }}>
        <div style={{ flex: 3 }}>
          <div style={{ ...pulse, height: '180px', borderRadius: 'var(--radius-md)' }} />
        </div>
        <div style={{ flex: 2 }}>
          <div style={{ ...pulse, height: '180px', borderRadius: 'var(--radius-md)' }} />
        </div>
      </div>
    </div>
  )
}
