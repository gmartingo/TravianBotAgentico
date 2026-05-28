/**
 * AgentBottomBar — barra inferior fija (position:fixed) visible en todas las pestañas.
 *
 * Layout (del mockup aprobado):
 *  [sección izquierda = --sidebar-w = 180px] [divisor 1px] [carrusel de pills →]
 *
 * Sección izquierda:
 *  - dot de estado (verde=running, rojo=stopped)
 *  - label clicable ("Bot activo" / "Bot parado")
 *  - clic → llama a onToggle
 *
 * Carrusel de pills (task queue):
 *  - Pill normal: nombre lista + countdown HH:MM:SS
 *  - Pill "is-next": borde dorado + hora exacta
 *  - Si agente parado: texto "Bot parado — sin tareas programadas"
 *
 * Props:
 *  - agentState  {string}  'running'|'stopped'|'error'
 *  - tasks       {Array}   [{id, list_name, next_run_iso, sched_name}]
 *  - onToggle    {Function}  — alterna arrancar/parar agente
 */
import { useI18n } from '../../i18n/index.jsx'
import { Countdown } from './Countdown.jsx'

// Constante del sidebar, debe coincidir con CSS --sidebar-w
const SIDEBAR_W = 180

export function AgentBottomBar({ agentState = 'stopped', tasks = [], onToggle }) {
  const { t } = useI18n()

  const isRunning = agentState === 'running'
  const dotColor  = isRunning ? 'var(--success)' : 'var(--danger)'
  const label     = isRunning ? t('bottomBar.running') : t('bottomBar.stopped')

  // Ordenar tasks por próximo disparo
  const sorted = [...tasks].sort((a, b) => {
    const ta = a.next_run_iso ? new Date(a.next_run_iso) : Infinity
    const tb = b.next_run_iso ? new Date(b.next_run_iso) : Infinity
    return ta - tb
  })

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        height: '48px',
        display: 'flex',
        alignItems: 'center',
        gap: 0,
        paddingInlineEnd: '24px',
        background: 'var(--surface)',
        borderTop: '1px solid var(--border)',
        zIndex: 200,
        transition: 'background var(--dur-base) var(--ease)',
      }}
    >
      {/* Sección izquierda — ancho exacto del sidebar */}
      <button
        type="button"
        onClick={onToggle}
        title={isRunning ? t('agent.stop') : t('agent.start')}
        aria-label={isRunning ? t('agent.stop') : t('agent.start')}
        style={{
          width: SIDEBAR_W,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          paddingInlineStart: '24px',
          paddingInlineEnd: '14px',
          height: '100%',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          borderRadius: 'var(--radius-sm)',
          transition: 'background var(--dur-fast) var(--ease)',
          boxSizing: 'border-box',
          fontFamily: 'inherit',
        }}
        className="hover:bg-[var(--surface-2)]"
      >
        {/* Dot de estado */}
        <span
          aria-hidden="true"
          style={{
            width: '7px',
            height: '7px',
            borderRadius: '50%',
            background: dotColor,
            flexShrink: 0,
          }}
        />
        {/* Label */}
        <span
          style={{
            fontSize: '13px',
            fontWeight: 500,
            color: dotColor,
            whiteSpace: 'nowrap',
          }}
        >
          {label}
        </span>
      </button>

      {/* Divisor vertical */}
      <div
        aria-hidden="true"
        style={{
          width: '1px',
          height: '20px',
          background: 'var(--border)',
          flexShrink: 0,
          alignSelf: 'center',
          marginInlineEnd: '14px',
        }}
      />

      {/* Carrusel de pills */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          overflowX: 'auto',
          scrollbarWidth: 'none',
          touchAction: 'pan-x',
        }}
      >
        {!isRunning ? (
          <span style={{ fontSize: '12px', color: 'var(--text-disabled)' }}>
            {t('bottomBar.empty')}
          </span>
        ) : sorted.length === 0 ? null : (
          sorted.map((task, idx) => {
            const isNext = idx === 0
            return (
              <TaskPill
                key={task.id ?? idx}
                listName={task.list_name}
                nextRunIso={task.next_run_iso}
                isNext={isNext}
              />
            )
          })
        )}
      </div>
    </div>
  )
}

// ── TaskPill ──────────────────────────────────────────────────────────────────

function TaskPill({ listName, nextRunIso, isNext }) {
  const pillStyle = {
    flexShrink: 0,
    width: '168px',
    height: '28px',
    padding: '0 10px',
    borderRadius: 'var(--radius-full)',
    border: `1px solid ${isNext ? 'var(--accent)' : 'var(--border)'}`,
    background: isNext ? 'var(--accent-subtle)' : 'var(--surface-2)',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    transition: 'border-color var(--dur-base), background var(--dur-base)',
  }

  const cdColor = isNext ? 'var(--accent-text)' : 'var(--text)'

  return (
    <div style={pillStyle}>
      <span style={{
        fontSize: '12px',
        fontWeight: 500,
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        flex: 1,
        minWidth: 0,
      }}>
        {listName}
      </span>
      <Countdown
        targetIso={nextRunIso}
        className=""
        style={{
          fontSize: '12px',
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
          color: cdColor,
          flexShrink: 0,
        }}
      />
    </div>
  )
}
