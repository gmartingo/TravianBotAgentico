/**
 * AgentsTab — V1 Schedulers.
 *
 * Contiene:
 *  - AgentStatusPanel: estado running/stopped/error + countdown próximo global + botones
 *  - Lista de SchedulerCards
 *  - Estado vacío, cargando (skeletons), error de red
 *  - SchedulerFormModal (V2): crear/editar
 *  - ConfirmDeleteModal: borrar scheduler
 *
 * Props:
 *  - worldId          {number}
 *  - agentState       {string}   'running'|'stopped'|'error'|'paused'
 *  - agentStatus      {object}   respuesta GET /agent/status
 *  - onAgentStart     {Function}
 *  - onAgentStop      {Function}
 *  - schedulers       {Array}
 *  - loadingSchedulers{boolean}
 *  - farmLists        {Array}    — para el modal V3
 *  - onSchedulersChange {Function} — callback para recargar schedulers
 */
import { useState, useRef, useEffect } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api, ApiError } from '../../api/client.js'
import { Spinner, useFocusTrap, showToast } from '../ui/uiUtils.jsx'
import { ConfirmDeleteModal } from '../ui/ConfirmDeleteModal.jsx'
import { Countdown } from './Countdown.jsx'
import { SchedulerSubPanel } from './SchedulerSubPanel.jsx'

// ── Iconos inline ─────────────────────────────────────────────────────────────

function IconClock({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}

function IconPlus({ size = 12 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function IconDots({ size = 15 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="currentColor" aria-hidden="true">
      <circle cx="12" cy="5" r="1.3" />
      <circle cx="12" cy="12" r="1.3" />
      <circle cx="12" cy="19" r="1.3" />
    </svg>
  )
}

function IconEdit({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  )
}

function IconPlay({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  )
}

function IconSend({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function IconTrash({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" /><path d="M14 11v6" />
    </svg>
  )
}

// ── SkeletonCard ──────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div
      aria-hidden="true"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '16px 20px',
      }}
    >
      <div style={{ display: 'flex', gap: '12px', marginBottom: '12px' }}>
        <span style={{ flex: 1, height: '16px', borderRadius: '4px', background: 'var(--surface-2)', animation: 'pulse 1.2s ease-in-out infinite' }} />
        <span style={{ width: '80px', height: '16px', borderRadius: '4px', background: 'var(--surface-2)', animation: 'pulse 1.2s ease-in-out infinite' }} />
      </div>
      <span style={{ display: 'block', width: '60%', height: '13px', borderRadius: '4px', background: 'var(--surface-2)', animation: 'pulse 1.2s ease-in-out infinite', marginBottom: '12px' }} />
      <div style={{ display: 'flex', gap: '8px', paddingTop: '10px', borderTop: '1px solid var(--border)' }}>
        <span style={{ width: '70px', height: '20px', borderRadius: '100px', background: 'var(--surface-2)', animation: 'pulse 1.2s ease-in-out infinite' }} />
        <span style={{ flex: 1 }} />
        <span style={{ width: '80px', height: '20px', borderRadius: '4px', background: 'var(--surface-2)', animation: 'pulse 1.2s ease-in-out infinite' }} />
      </div>
    </div>
  )
}

// ── SkeletonAgent ─────────────────────────────────────────────────────────────

function SkeletonAgent() {
  return (
    <div
      aria-hidden="true"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '14px 18px',
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        marginBottom: '24px',
      }}
    >
      <span style={{ width: '36px', height: '36px', borderRadius: '50%', background: 'var(--surface-2)', animation: 'pulse 1.2s ease-in-out infinite', flexShrink: 0 }} />
      <div style={{ flex: 1 }}>
        <span style={{ display: 'block', width: '120px', height: '14px', borderRadius: '4px', background: 'var(--surface-2)', animation: 'pulse 1.2s ease-in-out infinite', marginBottom: '6px' }} />
        <span style={{ display: 'block', width: '80px', height: '12px', borderRadius: '4px', background: 'var(--surface-2)', animation: 'pulse 1.2s ease-in-out infinite' }} />
      </div>
      <span style={{ width: '80px', height: '30px', borderRadius: '4px', background: 'var(--surface-2)', animation: 'pulse 1.2s ease-in-out infinite' }} />
    </div>
  )
}

// ── AgentStatusPanel ──────────────────────────────────────────────────────────

function AgentStatusPanel({ worldId, agentState, agentStatus, onStart, onStop, t }) {
  const configs = {
    running: {
      iconBg: 'rgba(36,138,61,.12)',
      iconColor: 'var(--success)',
      label: t('agent.status.running'),
      labelColor: 'var(--success)',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24"
          fill="currentColor" aria-hidden="true">
          <circle cx="12" cy="12" r="7" />
        </svg>
      ),
    },
    stopped: {
      iconBg: 'var(--surface-2)',
      iconColor: 'var(--text-secondary)',
      label: t('agent.status.stopped'),
      labelColor: 'var(--text-secondary)',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <circle cx="12" cy="12" r="7" />
        </svg>
      ),
    },
    error: {
      iconBg: 'rgba(201,53,44,.10)',
      iconColor: 'var(--danger)',
      label: t('agent.status.error'),
      labelColor: 'var(--danger)',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <circle cx="12" cy="17" r=".5" fill="currentColor" stroke="none" />
        </svg>
      ),
    },
    paused: {
      iconBg: 'rgba(10,111,204,.10)',
      iconColor: 'var(--info)',
      label: t('agent.status.paused'),
      labelColor: 'var(--info)',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24"
          fill="currentColor" aria-hidden="true">
          <rect x="6" y="4" width="4" height="16" />
          <rect x="14" y="4" width="4" height="16" />
        </svg>
      ),
    },
  }
  const cfg = configs[agentState] ?? configs.stopped
  const queued = agentStatus?.queued_tasks ?? 0
  const nextAt = agentStatus?.next_task_at ?? null
  const lastErr = agentStatus?.last_error ?? null

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      padding: '14px 18px',
      display: 'flex',
      alignItems: 'center',
      gap: '16px',
      marginBottom: '24px',
      flexWrap: 'wrap',
    }}
      role="status"
      aria-label={cfg.label}
    >
      {/* Icono de estado */}
      <div style={{
        width: '36px', height: '36px',
        borderRadius: '50%',
        background: cfg.iconBg,
        color: cfg.iconColor,
        display: 'grid',
        placeItems: 'center',
        flexShrink: 0,
      }}>
        {cfg.icon}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '14px', fontWeight: 500, color: cfg.labelColor }}>
          {cfg.label}
        </div>
        {agentState === 'running' && (
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            {t('agent.schedulersActive').replace('{n}', queued)}
          </div>
        )}
        {agentState === 'error' && lastErr && (
          <div style={{
            fontSize: '11px',
            color: 'var(--danger)',
            marginTop: '3px',
            fontFamily: 'var(--font-mono)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            maxWidth: '300px',
          }}>
            {t('agent.lastError')} {lastErr}
          </div>
        )}
      </div>

      {/* Countdown próximo envío */}
      {agentState === 'running' && nextAt && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            {t('agent.nextGlobal')}
          </span>
          <Countdown
            targetIso={nextAt}
            className=""
            style={{
              fontSize: '20px',
              fontWeight: 600,
              fontFamily: 'var(--font-mono)',
              color: 'var(--text)',
            }}
          />
        </div>
      )}

      {/* Botones */}
      <div style={{ flexShrink: 0 }}>
        {agentState === 'stopped' && (
          <button
            type="button"
            onClick={onStart}
            style={{
              height: '32px', padding: '0 14px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--btn-primary-bg)',
              color: 'var(--btn-primary-text)',
              border: 'none',
              fontSize: '13px',
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '6px',
              fontFamily: 'inherit',
              transition: 'background var(--dur-fast)',
            }}
          >
            {t('agent.start')}
          </button>
        )}
        {agentState === 'running' && (
          <button
            type="button"
            onClick={onStop}
            style={{
              height: '32px', padding: '0 14px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-strong)',
              background: 'var(--surface)',
              color: 'var(--text)',
              fontSize: '13px',
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '6px',
              fontFamily: 'inherit',
              transition: 'background var(--dur-fast)',
            }}
          >
            {t('agent.stop')}
          </button>
        )}
        {agentState === 'error' && (
          <button
            type="button"
            onClick={onStart}
            style={{
              height: '32px', padding: '0 14px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-strong)',
              background: 'var(--surface)',
              color: 'var(--text)',
              fontSize: '13px',
              cursor: 'pointer',
              fontFamily: 'inherit',
              transition: 'background var(--dur-fast)',
            }}
          >
            {t('agent.retry')}
          </button>
        )}
      </div>
    </div>
  )
}

// ── ToggleSwitch ──────────────────────────────────────────────────────────────
// Switch macOS-style con role="switch" y aria-checked.

function ToggleSwitch({ checked, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      title={label}
      style={{
        width: '36px',
        height: '20px',
        borderRadius: 'var(--radius-full)',
        border: `1px solid ${checked ? 'var(--success)' : 'var(--border-strong)'}`,
        background: checked ? 'var(--success)' : 'var(--surface-2)',
        position: 'relative',
        cursor: 'pointer',
        flexShrink: 0,
        transition: 'background var(--dur-base), border-color var(--dur-base)',
        padding: 0,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: '2px',
          insetInlineStart: checked ? '18px' : '2px',
          width: '14px',
          height: '14px',
          borderRadius: '50%',
          background: '#fff',
          transition: 'inset-inline-start var(--dur-base)',
        }}
      />
    </button>
  )
}

// ── RowMenu (⋯) ──────────────────────────────────────────────────────────────

function SchedulerRowMenu({ worldId, schedulerId, schedulerName, agentState, onEdit, onDelete, onRunNow, t }) {
  const [open, setOpen] = useState(false)
  const [running, setRunning] = useState(false)
  const btnRef = useRef(null)
  const menuRef = useRef(null)

  useEffect(() => {
    if (!open) return
    function handler(e) {
      if (!menuRef.current?.contains(e.target) && !btnRef.current?.contains(e.target))
        setOpen(false)
    }
    function keyHandler(e) {
      if (e.key === 'Escape') { setOpen(false); btnRef.current?.focus() }
    }
    document.addEventListener('mousedown', handler)
    document.addEventListener('keydown', keyHandler)
    return () => {
      document.removeEventListener('mousedown', handler)
      document.removeEventListener('keydown', keyHandler)
    }
  }, [open])

  useEffect(() => {
    if (open) setTimeout(() => menuRef.current?.querySelector('[role="menuitem"]')?.focus(), 0)
  }, [open])

  async function handleRunNow() {
    setOpen(false)
    if (agentState !== 'running') {
      showToast('El agente no está activo. Arráncalo primero.')
      return
    }
    setRunning(true)
    try {
      await api.runSchedulerNow(worldId, schedulerId)
      showToast(t('schedulers.card.run') + ' — OK')
    } catch {
      showToast(t('schedulers.error.saveFailed'))
    } finally {
      setRunning(false)
    }
  }

  const menuItemBase = {
    display: 'flex', alignItems: 'center', gap: '8px',
    width: '100%', padding: '8px 12px',
    border: 'none', background: 'transparent',
    color: 'var(--text)',
    fontFamily: 'inherit', fontSize: '13px',
    cursor: 'pointer', textAlign: 'start',
  }

  return (
    <div style={{ position: 'relative', display: 'inline-flex' }}>
      <button
        ref={btnRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('schedulers.card.edit')}
        onClick={e => { e.stopPropagation(); setOpen(v => !v) }}
        style={{
          width: '32px', height: '32px',
          borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--border)',
          background: 'var(--surface)',
          color: 'var(--text-secondary)',
          display: 'grid', placeItems: 'center',
          cursor: 'pointer',
          transition: 'background var(--dur-fast)',
        }}
      >
        <IconDots />
      </button>

      {open && (
        <div
          ref={menuRef}
          role="menu"
          style={{
            position: 'absolute',
            insetInlineEnd: 0,
            top: 'calc(100% + 4px)',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-md)',
            minWidth: '140px',
            overflow: 'hidden',
            zIndex: 200,
          }}
        >
          <button
            role="menuitem"
            type="button"
            onClick={() => { setOpen(false); onEdit() }}
            style={menuItemBase}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-2)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
          >
            <IconEdit /> {t('schedulers.card.edit')}
          </button>
          <button
            role="menuitem"
            type="button"
            onClick={handleRunNow}
            disabled={running}
            style={{ ...menuItemBase, opacity: running ? 0.5 : 1, cursor: running ? 'not-allowed' : 'pointer' }}
            onMouseEnter={e => { if (!running) e.currentTarget.style.background = 'var(--surface-2)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
          >
            {running ? <Spinner size={13} /> : <IconPlay />}
            {t('schedulers.card.run')}
          </button>
          <button
            role="menuitem"
            type="button"
            onClick={() => { setOpen(false); onDelete() }}
            style={{ ...menuItemBase, color: 'var(--danger)' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-2)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
          >
            <IconTrash /> {t('schedulers.card.delete')}
          </button>
        </div>
      )}
    </div>
  )
}

// ── SchedulerCard ─────────────────────────────────────────────────────────────
// Ahora es un accordion: clic en el header despliega el sub-panel operativo.
// El botón ⏸/▶ está visible en el header sin abrir el sub-panel.

function SchedulerCard({
  scheduler, worldId, agentState, onEdit, onDelete, onToggle,
  farmLists, onNavigateToFarmList, onOpenDashboard, t,
}) {
  const {
    id, name, is_enabled, interval_min_ms, interval_max_ms,
    next_run, execution_count, farm_list_ids,
  } = scheduler

  const [expanded, setExpanded] = useState(false)
  const [sending, setSending] = useState(false)
  const [toggling, setToggling] = useState(false)

  async function handleSendAll(e) {
    e.stopPropagation()
    if (!farm_list_ids?.length || sending) return
    setSending(true)
    let errors = 0
    for (const flId of farm_list_ids) {
      try {
        await api.sendFarmList(flId, worldId)
      } catch {
        errors++
      }
    }
    setSending(false)
    if (errors === 0) {
      showToast(t('schedulers.card.sendNow.toast.ok'))
    } else {
      showToast(t('schedulers.card.sendNow.toast.partial').replace('{errors}', errors).replace('{total}', farm_list_ids.length))
    }
  }

  // Toggle is_enabled (botón ⏸/▶): usa el mismo endpoint que el toggle switch
  async function handlePauseActivate(e) {
    e.stopPropagation()
    if (toggling) return
    setToggling(true)
    try {
      await api.updateScheduler(worldId, id, {
        name,
        interval_min_ms,
        interval_max_ms,
        is_enabled: !is_enabled,
      })
      onToggle()
    } catch {
      showToast(t('schedulers.error.saveFailed'))
    } finally {
      setToggling(false)
    }
  }

  // Calcular meta
  const listCount = farm_list_ids?.length ?? 0
  const meta = t('schedulers.card.meta')
    .replace('{n}', listCount)
    .replace('{min}', formatMmSs(interval_min_ms))
    .replace('{max}', formatMmSs(interval_max_ms))
    .replace('{count}', execution_count ?? 0)

  const isRunning = is_enabled && agentState === 'running'
  const hasList = (farm_list_ids?.length ?? 0) > 0

  return (
    <div
      style={{
        opacity: is_enabled ? 1 : 0.7,
      }}
    >
      {/* ── HEADER DEL CARD (clicar para expandir/colapsar) ── */}
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded(v => !v)}
        style={{
          display: 'flex', alignItems: 'center', gap: '12px',
          width: '100%', textAlign: 'start',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: expanded ? 'var(--radius-md) var(--radius-md) 0 0' : 'var(--radius-md)',
          padding: '14px 16px',
          cursor: 'pointer',
          fontFamily: 'inherit',
          transition: 'background var(--dur-fast)',
          userSelect: 'none',
        }}
        className="hover:bg-[var(--surface-2)]"
      >
        {/* Dot estado */}
        <span
          aria-hidden="true"
          style={{
            width: '8px', height: '8px',
            borderRadius: '50%',
            background: isRunning ? 'var(--success)' : 'var(--text-disabled)',
            flexShrink: 0,
          }}
        />

        {/* Nombre + meta */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text)' }}>{name}</div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            {meta}
          </div>
        </div>

        {/* Badge deact si hay */}
        {scheduler.kpi_deact > 0 && (
          <span style={{
            background: 'rgba(201,53,44,.1)', color: 'var(--danger)',
            fontSize: '11px', padding: '1px 7px',
            borderRadius: 'var(--radius-full)', fontWeight: 600,
            flexShrink: 0,
          }}>
            {scheduler.kpi_deact} desact.
          </span>
        )}

        {/* Próximo */}
        <span style={{
          fontSize: '12px', color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-mono)', flexShrink: 0, whiteSpace: 'nowrap',
        }}>
          {isRunning && next_run
            ? `próx. ${new Date(next_run).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
            : 'parado'
          }
        </span>

        {/* Chevron */}
        <span
          aria-hidden="true"
          style={{
            fontSize: '11px', color: 'var(--text-tertiary)',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform var(--dur-fast)',
            flexShrink: 0,
          }}
        >
          ▼
        </span>

        {/* Acciones del card */}
        <div
          onClick={e => e.stopPropagation()}
          style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}
        >
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); handleSendAll(e) }}
            disabled={!hasList || sending}
            title={!hasList ? t('schedulers.card.sendNow.noLists') : t('schedulers.card.sendNow')}
            style={{
              fontSize: '11px', height: '26px', padding: '0 8px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-strong)',
              background: 'var(--surface)',
              color: (!hasList || sending) ? 'var(--text-disabled)' : 'var(--text)',
              cursor: (!hasList || sending) ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit',
              display: 'flex', alignItems: 'center', gap: '4px',
              transition: 'background var(--dur-fast)',
              opacity: !hasList ? 0.5 : 1,
            }}
            onMouseEnter={e => { if (hasList && !sending) e.currentTarget.style.background = 'var(--surface-2)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)' }}
          >
            {sending ? <Spinner size={10} /> : <IconSend size={10} />}
            {t('schedulers.card.sendNow')}
          </button>
          <SchedulerRowMenu
            worldId={worldId}
            schedulerId={id}
            schedulerName={name}
            agentState={agentState}
            onEdit={onEdit}
            onDelete={onDelete}
            onRunNow={() => {}}
            t={t}
          />
          <ToggleSwitch
            checked={is_enabled}
            onChange={() => handlePauseActivate({ stopPropagation: () => {} })}
            label={is_enabled ? 'Desactivar scheduler' : 'Activar scheduler'}
          />
        </div>
      </button>

      {/* ── CHIPS de listas (debajo del header cuando NO expandido) ── */}
      {!expanded && (farm_list_ids ?? []).length > 0 && (
        <div style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)', borderTop: 'none',
          borderRadius: '0 0 var(--radius-md) var(--radius-md)',
          padding: '8px 14px 10px',
        }}
          className="hidden sm:block"
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            {(farm_list_ids ?? []).map(flId => {
              const fl = (farmLists ?? []).find(f => f.id === flId)
              const label = fl
                ? `${fl.name}${fl.village_name ? ' · ' + fl.village_name : ''}`
                : `#${flId}`
              return (
                <button
                  key={flId}
                  type="button"
                  onClick={() => onNavigateToFarmList?.(flId)}
                  title={label}
                  style={{
                    display: 'inline-flex', alignItems: 'center',
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-full)',
                    padding: '2px 10px',
                    fontSize: '11px', color: 'var(--text-secondary)',
                    whiteSpace: 'nowrap', cursor: 'pointer',
                    maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis',
                    fontFamily: 'inherit',
                    transition: 'background var(--dur-fast), color var(--dur-fast)',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent-subtle)'; e.currentTarget.style.color = 'var(--accent-text)'; e.currentTarget.style.borderColor = 'var(--accent)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--text-secondary)'; e.currentTarget.style.borderColor = 'var(--border)' }}
                >
                  {label}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* ── SUB-PANEL EXPANDIDO ── */}
      {expanded && (
        <SchedulerSubPanel
          scheduler={scheduler}
          worldId={worldId}
          farmLists={farmLists}
          onOpenDashboard={() => onOpenDashboard?.(scheduler)}
          t={t}
        />
      )}
    </div>
  )
}

// ── helpers MM:SS ─────────────────────────────────────────────────────────────

function msToMmSs(ms) {
  const totalSec = Math.round(ms / 1000)
  return { mm: Math.floor(totalSec / 60), ss: totalSec % 60 }
}

function formatMmSs(ms) {
  const { mm, ss } = msToMmSs(ms)
  return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

// ── SchedulerFormModal (V2) ───────────────────────────────────────────────────

function SchedulerFormModal({ worldId, scheduler, farmLists, schedulers, onClose, onSaved, t }) {
  const isEdit = !!scheduler
  const modalRef = useRef(null)
  useFocusTrap(modalRef, true)

  const [name, setName] = useState(scheduler?.name ?? '')
  const [minMMSS, setMinMMSS] = useState(formatMmSs(scheduler?.interval_min_ms ?? 180000))
  const [maxMMSS, setMaxMMSS] = useState(formatMmSs(scheduler?.interval_max_ms ?? 300000))
  const [selectedLists, setSelectedLists] = useState(new Set(scheduler?.farm_list_ids ?? []))
  const [listsExpanded, setListsExpanded] = useState(false)
  const [collapsedGroups, setCollapsedGroups] = useState(new Set())
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState({})

  useEffect(() => {
    function handler(e) {
      if (e.key === 'Escape' && !saving) onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [saving, onClose])

  function parseMMSS(str) {
    const [mStr = '0', sStr = '0'] = str.split(':')
    return (parseInt(mStr, 10) * 60 + parseInt(sStr, 10)) * 1000
  }

  function isValidMMSS(str) {
    if (!/^\d{1,3}:\d{2}$/.test(str)) return false
    return parseInt(str.split(':')[1], 10) < 60
  }

  function handleMMSSChange(setter) {
    return (e) => {
      let val = e.target.value.replace(/[^\d:]/g, '')
      if (val.length === 2 && !val.includes(':') && e.nativeEvent?.inputType !== 'deleteContentBackward') {
        val = val + ':'
      }
      if (val.length > 5) val = val.slice(0, 5)
      setter(val)
    }
  }

  function getOtherScheduler(farmListId) {
    return (schedulers ?? []).find(s =>
      s.id !== scheduler?.id && s.farm_list_ids?.includes(farmListId)
    )?.name ?? null
  }

  function toggleList(id) {
    setSelectedLists(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function validate() {
    const errs = {}
    if (!name.trim()) errs.name = t('wizard.error.required')
    if (!isValidMMSS(minMMSS)) errs.min = 'Formato inválido — usa MM:SS (ej. 04:30)'
    if (!isValidMMSS(maxMMSS)) errs.max = 'Formato inválido — usa MM:SS (ej. 06:00)'
    if (isValidMMSS(minMMSS) && isValidMMSS(maxMMSS)) {
      if (parseMMSS(minMMSS) < 60000) errs.min = t('schedulers.error.intervalTooShort')
      if (parseMMSS(maxMMSS) < 60000) errs.max = t('schedulers.error.intervalTooShort')
      if (parseMMSS(minMMSS) > parseMMSS(maxMMSS)) errs.max = t('schedulers.error.intervalMin')
    }
    return errs
  }

  async function handleSave() {
    const errs = validate()
    if (Object.keys(errs).length > 0) { setErrors(errs); return }
    setSaving(true)
    const data = {
      name: name.trim(),
      interval_min_ms: parseMMSS(minMMSS),
      interval_max_ms: parseMMSS(maxMMSS),
      is_enabled: scheduler?.is_enabled ?? true,
    }
    try {
      let saved
      if (isEdit) {
        saved = await api.updateScheduler(worldId, scheduler.id, data)
      } else {
        saved = await api.createScheduler(worldId, data)
      }
      await api.assignFarmLists(worldId, saved.id, [...selectedLists])
      onSaved(saved)
      onClose()
    } catch {
      showToast(t('schedulers.error.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const inputBase = {
    width: '100%', height: '34px',
    border: '1px solid var(--border-strong)',
    background: 'var(--surface-2)',
    color: 'var(--text)',
    borderRadius: 'var(--radius-sm)',
    padding: '0 10px',
    fontFamily: 'inherit', fontSize: '13px',
    outline: 'none', boxSizing: 'border-box',
  }
  const mmssStyle = {
    ...inputBase,
    fontFamily: 'var(--font-mono)', fontSize: '15px',
    fontVariantNumeric: 'tabular-nums', letterSpacing: '.04em',
    textAlign: 'center',
  }
  const labelStyle = { display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--text)' }
  const errorStyle = { fontSize: '11px', color: 'var(--danger)', marginTop: '4px' }
  const focusHandlers = {
    onFocus: e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '1px' },
    onBlur: e => { e.currentTarget.style.borderColor = 'var(--border-strong)'; e.currentTarget.style.outline = 'none' },
  }
  const btnSecBase = {
    height: '32px', padding: '0 14px', borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-strong)', background: 'var(--surface)', color: 'var(--text)',
    fontSize: '13px', cursor: 'pointer', fontFamily: 'inherit',
    display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap',
    transition: 'background var(--dur-fast)',
  }
  const btnPrimBase = {
    height: '32px', padding: '0 14px', borderRadius: 'var(--radius-sm)',
    border: 'none', background: 'var(--btn-primary-bg)', color: 'var(--btn-primary-text)',
    fontSize: '13px', fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
    display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap',
    transition: 'background var(--dur-fast)',
  }

  return (
    <div
      role="dialog" aria-modal="true" aria-labelledby="schedFormTitle"
      style={{
        position: 'fixed', inset: 0, zIndex: 400,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,.4)',
      }}
      onClick={e => { if (e.target === e.currentTarget && !saving) onClose() }}
    >
      <div
        ref={modalRef}
        style={{
          background: 'var(--surface)', borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-lg)', width: 'min(440px,92vw)', maxHeight: '90vh',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
        onClick={e => e.stopPropagation()}
        className="max-sm:w-full max-sm:rounded-b-none max-sm:self-end"
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px',
          padding: '16px 20px', borderBottom: '1px solid var(--border)', flexShrink: 0,
        }}>
          <span id="schedFormTitle" style={{ fontSize: '17px', fontWeight: 600, letterSpacing: '-0.01em' }}>
            {isEdit ? t('schedulers.form.title.edit') : t('schedulers.form.title.create')}
          </span>
          <button type="button" onClick={onClose} aria-label="Cerrar"
            style={{ width: '28px', height: '28px', borderRadius: 'var(--radius-sm)', background: 'transparent', border: 'none', display: 'grid', placeItems: 'center', fontSize: '18px', cursor: 'pointer', color: 'var(--text-secondary)' }}>
            &times;
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>
          {/* Nombre */}
          <div style={{ marginBottom: '16px' }}>
            <label style={labelStyle} htmlFor="sched-name">{t('schedulers.form.name')}</label>
            <input
              id="sched-name" style={inputBase} type="text"
              placeholder={t('schedulers.form.name.ph')}
              value={name} onChange={e => setName(e.target.value)}
              {...focusHandlers}
            />
            {errors.name && <div style={errorStyle}>{errors.name}</div>}
          </div>

          {/* Intervalos — un solo input MM:SS por intervalo */}
          <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle} htmlFor="sched-min">{t('schedulers.form.intervalMin')}</label>
              <input
                id="sched-min" style={mmssStyle} type="text"
                placeholder="04:30" value={minMMSS}
                onChange={handleMMSSChange(setMinMMSS)}
                {...focusHandlers}
              />
              {errors.min && <div style={errorStyle}>{errors.min}</div>}
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle} htmlFor="sched-max">{t('schedulers.form.intervalMax')}</label>
              <input
                id="sched-max" style={mmssStyle} type="text"
                placeholder="06:00" value={maxMMSS}
                onChange={handleMMSSChange(setMaxMMSS)}
                {...focusHandlers}
              />
              {errors.max && <div style={errorStyle}>{errors.max}</div>}
            </div>
          </div>

          {/* Listas asignadas — desplegable */}
          <div style={{
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            overflow: 'hidden',
          }}>
            <button
              type="button"
              onClick={() => setListsExpanded(v => !v)}
              style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                width: '100%', padding: '10px 14px',
                border: 'none', background: 'transparent',
                cursor: 'pointer', fontFamily: 'inherit',
                borderBottom: listsExpanded ? '1px solid var(--border)' : 'none',
                transition: 'background var(--dur-fast)',
              }}
              className="hover:bg-[var(--surface-2)]"
            >
              <span style={{ fontSize: '13px', fontWeight: 500, flex: 1, textAlign: 'start', color: 'var(--text)' }}>
                {t('schedulers.assign.title').replace('{name}', '').trim() || 'Listas asignadas'}
                {selectedLists.size > 0 && (
                  <span style={{
                    marginLeft: '8px',
                    display: 'inline-flex', alignItems: 'center',
                    background: 'var(--surface-2)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-full)',
                    fontSize: '11px', padding: '0 6px',
                    color: 'var(--text-secondary)',
                  }}>
                    {selectedLists.size}
                  </span>
                )}
              </span>
              <span aria-hidden="true" style={{
                fontSize: '10px', color: 'var(--text-tertiary)',
                transform: listsExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                transition: 'transform var(--dur-fast)',
              }}>▼</span>
            </button>

            {listsExpanded && (
              <div style={{ maxHeight: '220px', overflowY: 'auto' }}>
                {(farmLists ?? []).length === 0 ? (
                  <p style={{ padding: '12px 14px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {t('schedulers.assign.noLists')}
                  </p>
                ) : (() => {
                  // Agrupar por aldea
                  const groups = (farmLists ?? []).reduce((acc, fl) => {
                    const key = fl.village_name ?? `#${fl.owner_village_id}`
                    ;(acc[key] = acc[key] ?? []).push(fl)
                    return acc
                  }, {})
                  return Object.entries(groups).map(([villageName, lists]) => {
                    const isGroupCollapsed = collapsedGroups.has(villageName)
                    return (
                    <div key={villageName}>
                      <button
                        type="button"
                        onClick={() => setCollapsedGroups(prev => {
                          const next = new Set(prev)
                          if (next.has(villageName)) next.delete(villageName)
                          else next.add(villageName)
                          return next
                        })}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '6px',
                          width: '100%', padding: '5px 14px 4px',
                          border: 'none', background: 'var(--surface-2)',
                          borderBottom: '1px solid var(--border)',
                          cursor: 'pointer', fontFamily: 'inherit',
                          position: 'sticky', top: 0,
                          transition: 'background var(--dur-fast)',
                        }}
                        className="hover:bg-[var(--border)]"
                      >
                        <span style={{
                          fontSize: '10px', color: 'var(--text-tertiary)',
                          transform: isGroupCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)',
                          transition: 'transform var(--dur-fast)',
                          flexShrink: 0,
                        }} aria-hidden="true">▼</span>
                        <span style={{
                          fontSize: '10px', fontWeight: 600,
                          color: 'var(--text-tertiary)',
                          textTransform: 'uppercase', letterSpacing: '.06em',
                          flex: 1, textAlign: 'start',
                        }}>
                          {villageName}
                        </span>
                        <span style={{ fontSize: '10px', color: 'var(--text-disabled)' }}>
                          {lists.filter(fl => selectedLists.has(fl.id)).length}/{lists.length}
                        </span>
                      </button>
                      {!isGroupCollapsed && lists.map(fl => {
                        const inOther = getOtherScheduler(fl.id)
                        const isDisabled = !!inOther
                        const isChecked = selectedLists.has(fl.id)
                        return (
                          <label
                            key={fl.id}
                            style={{
                              display: 'flex', alignItems: 'center', gap: '10px',
                              padding: '9px 14px', borderBottom: '1px solid var(--border)',
                              cursor: isDisabled ? 'not-allowed' : 'pointer',
                              opacity: isDisabled ? 0.5 : 1, background: 'transparent',
                            }}
                            onMouseEnter={e => { if (!isDisabled) e.currentTarget.style.background = 'var(--surface-2)' }}
                            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
                          >
                            <input
                              type="checkbox" checked={isChecked} disabled={isDisabled}
                              onChange={() => !isDisabled && toggleList(fl.id)}
                              style={{ accentColor: 'var(--accent)', width: '15px', height: '15px', flexShrink: 0, cursor: isDisabled ? 'not-allowed' : 'pointer' }}
                            />
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontSize: '13px', color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {fl.name}
                              </div>
                            </div>
                            {inOther && (
                              <span style={{
                                fontSize: '10px', color: 'var(--text-tertiary)',
                                background: 'var(--surface-2)', border: '1px solid var(--border)',
                                borderRadius: 'var(--radius-full)', padding: '1px 6px',
                                whiteSpace: 'nowrap', flexShrink: 0,
                              }}>
                                {t('schedulers.assign.inOther').replace('{sched}', inOther)}
                              </span>
                            )}
                          </label>
                        )
                      })}
                    </div>
                  )})
                })()}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px',
          padding: '14px 20px', borderTop: '1px solid var(--border)', flexShrink: 0,
        }}>
          <button type="button" onClick={onClose} disabled={saving} style={btnSecBase}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-2)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)' }}>
            {t('schedulers.form.cancel')}
          </button>
          <button type="button" onClick={handleSave} disabled={saving} style={{ ...btnPrimBase, opacity: saving ? 0.7 : 1 }}
            onMouseEnter={e => { if (!saving) e.currentTarget.style.background = 'var(--btn-primary-hover)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--btn-primary-bg)' }}>
            {saving && <Spinner size={13} />}
            {t('schedulers.form.save')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── AgentsTab ─────────────────────────────────────────────────────────────────

export function AgentsTab({
  worldId,
  agentState,
  agentStatus,
  onAgentStart,
  onAgentStop,
  schedulers,
  loadingSchedulers,
  farmLists,
  onSchedulersChange,
  onNavigateToFarmList,
  onOpenSchedulerDashboard,
}) {
  const { t } = useI18n()

  // Modales
  const [editModal, setEditModal] = useState(null)      // null | scheduler a editar | 'new'
  const [deleteModal, setDeleteModal] = useState(null)  // null | { id, name }

  // refs para devolver foco
  const newBtnRef = useRef(null)

  async function handleToggleEnabled(scheduler) {
    const updated = {
      name: scheduler.name,
      interval_min_ms: scheduler.interval_min_ms,
      interval_max_ms: scheduler.interval_max_ms,
      is_enabled: !scheduler.is_enabled,
    }
    try {
      await api.updateScheduler(worldId, scheduler.id, updated)
      onSchedulersChange()
    } catch {
      showToast(t('schedulers.error.saveFailed'))
    }
  }

  async function handleDelete() {
    if (!deleteModal) return
    await api.deleteScheduler(worldId, deleteModal.id)
    showToast(t('schedulers.card.delete') + ' — OK')
    onSchedulersChange()
    setDeleteModal(null)
  }

  if (loadingSchedulers) {
    return (
      <div>
        <SkeletonAgent />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Section header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
        <span style={{ fontSize: '17px', fontWeight: 600, letterSpacing: '-0.01em', flex: 1 }}>
          {t('schedulers.title')}
        </span>
        <button
          ref={newBtnRef}
          type="button"
          onClick={() => setEditModal('new')}
          style={{
            height: '32px', padding: '0 14px',
            borderRadius: 'var(--radius-sm)', border: 'none',
            background: 'var(--btn-primary-bg)', color: 'var(--btn-primary-text)',
            fontSize: '13px', cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', gap: '6px',
            transition: 'background var(--dur-fast)',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--btn-primary-hover)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'var(--btn-primary-bg)' }}
        >
          <IconPlus />
          {t('schedulers.new')}
        </button>
      </div>

      {/* Empty state */}
      {schedulers.length === 0 && (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', padding: '64px 24px', textAlign: 'center', gap: '12px',
        }}>
          <div style={{ width: '48px', height: '48px', color: 'var(--text-disabled)', marginBottom: '4px' }}>
            <IconClock size={48} />
          </div>
          <div style={{ fontSize: '17px', fontWeight: 600, letterSpacing: '-0.01em' }}>
            {t('schedulers.empty.title')}
          </div>
          <div style={{ fontSize: '14px', color: 'var(--text-secondary)', maxWidth: '280px', lineHeight: 1.5 }}>
            {t('schedulers.empty.sub')}
          </div>
          <button
            type="button"
            onClick={() => setEditModal('new')}
            style={{
              marginTop: '8px', height: '32px', padding: '0 14px',
              borderRadius: 'var(--radius-sm)', border: 'none',
              background: 'var(--btn-primary-bg)', color: 'var(--btn-primary-text)',
              fontSize: '13px', cursor: 'pointer', fontFamily: 'inherit',
              display: 'flex', alignItems: 'center', gap: '6px',
            }}
          >
            <IconPlus /> {t('schedulers.empty.cta')}
          </button>
        </div>
      )}

      {/* Lista de scheduler cards */}
      {schedulers.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {schedulers.map(sched => (
            <SchedulerCard
              key={sched.id}
              scheduler={sched}
              worldId={worldId}
              agentState={agentState}
              onEdit={() => setEditModal(sched)}
              onDelete={() => setDeleteModal({ id: sched.id, name: sched.name })}
              onToggle={() => handleToggleEnabled(sched)}
              farmLists={farmLists}
              onNavigateToFarmList={onNavigateToFarmList}
              onOpenDashboard={onOpenSchedulerDashboard}
              t={t}
            />
          ))}
        </div>
      )}

      {/* ── Modales ── */}

      {/* Crear / Editar scheduler (con asignación de listas integrada) */}
      {editModal !== null && (
        <SchedulerFormModal
          worldId={worldId}
          scheduler={editModal === 'new' ? null : editModal}
          farmLists={farmLists}
          schedulers={schedulers}
          onClose={() => setEditModal(null)}
          onSaved={() => { onSchedulersChange(); setEditModal(null) }}
          t={t}
        />
      )}

      {/* Confirmar borrado */}
      {deleteModal && (
        <ConfirmDeleteModal
          title={t('schedulers.delete.title')}
          question={t('schedulers.delete.question').replace('{name}', deleteModal.name)}
          warning={t('schedulers.delete.warning')}
          onConfirm={handleDelete}
          onClose={() => setDeleteModal(null)}
          triggerRef={newBtnRef}
        />
      )}
    </div>
  )
}
