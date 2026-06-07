/**
 * AccountDetailPage — S4 Detalle de cuenta (implementación real).
 *
 * Spec:  docs/design/gestion-cuentas-mundos.md §4/§4b, §6 S4, §7 S4, §9 S4
 * Mockup: frontend/mockups/cuenta-detalle.playground.html
 *
 * Estados cubiertos:
 *  - Cargando:   skeleton cabecera + skeleton tabla
 *  - 404:        "Cuenta no encontrada" + CTA volver
 *  - Error red:  toast
 *  - Sin mundos: empty state con CTA "Añadir mundo"
 *  - Con mundos: tabla desktop / tarjetas móvil; SessionStatusBadge + WorldSessionButton
 *
 * Estados de sesión (§4b):
 *  idle → connecting → active → stopping → idle
 *         connecting → error  → connecting (Reintentar)
 *  GET /session al montar (silencioso; 404/501 → idle, no rompe la UI)
 *  POST /session = Arrancar (síncrono, hasta ~30s). Conectando mientras espera.
 *  DELETE /session = Parar.
 *  Al 200 de Arrancar → estado Activo + navega a /mundos/:worldId si todo bien.
 *  Al 401 de Arrancar → estado Error, permanece en S4.
 *
 * Modales:
 *  S5 EditAccountModal, S6 AddWorldModal, S7 ConfirmDeleteModal (cuenta), S8 ídem (mundo)
 *
 * Reglas de implementación:
 *  - CERO texto hardcodeado — todo pasa por t().
 *  - NO overflow-x-auto / overflow-hidden en wrappers que envuelvan menús/popovers.
 *  - NO @layer base tocado.
 *  - Sidebar, i18n, tema, lista y wizard NO se tocan.
 *  - Claves i18n referencian el catálogo ya existente en src/i18n/catalog/es.js.
 */
import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useI18n } from '../i18n/index.jsx'
import { api, ApiError } from '../api/client.js'
import { parseServerUrl, BadgeSpinner, showToast } from '../components/ui/uiUtils.jsx'
import { AddWorldModal }       from '../components/ui/AddWorldModal.jsx'
import { ConfirmDeleteModal }  from '../components/ui/ConfirmDeleteModal.jsx'
import { AttackBadge }         from '../components/world/AttackBadge.jsx'

// ─── Iconos inline ───────────────────────────────────────────────────────────

function IconGlobe({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  )
}

function IconWarning({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

function IconPlus({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function IconDots({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="currentColor" aria-hidden="true">
      <circle cx="5"  cy="12" r="1.5" />
      <circle cx="12" cy="12" r="1.5" />
      <circle cx="19" cy="12" r="1.5" />
    </svg>
  )
}

// ─── Flecha breadcrumb (se espeja en RTL) ────────────────────────────────────
function ArrowBack({ isRTL }) {
  return isRTL ? (
    <svg width="14" height="14" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  ) : (
    <svg width="14" height="14" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  )
}

// ─── SessionStatusBadge ───────────────────────────────────────────────────────
// Regla DESIGN.md §5: SIEMPRE icono + texto, NUNCA solo color.
function SessionStatusBadge({ state, t }) {
  const configs = {
    idle: {
      color: 'var(--text-tertiary)',
      icon: (
        <svg width="11" height="11" viewBox="0 0 12 12"
          fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <circle cx="6" cy="6" r="5" />
        </svg>
      ),
      label: t('world.session.idle'),
    },
    connecting: {
      color: 'var(--accent)',
      icon: <BadgeSpinner />,
      label: t('world.session.connecting'),
    },
    active: {
      color: 'var(--success)',
      icon: (
        <svg width="11" height="11" viewBox="0 0 12 12"
          fill="currentColor" aria-hidden="true">
          <circle cx="6" cy="6" r="5" />
        </svg>
      ),
      label: t('world.session.active'),
    },
    error: {
      color: 'var(--danger)',
      icon: (
        <svg width="11" height="11" viewBox="0 0 16 14"
          fill="none" stroke="currentColor" strokeWidth="1.8"
          strokeLinecap="round" aria-hidden="true">
          <path d="M8 1L1 13h14L8 1z" />
          <line x1="8" y1="5.5" x2="8" y2="8.5" />
          <circle cx="8" cy="11" r=".5" fill="currentColor" stroke="none" />
        </svg>
      ),
      label: t('world.session.error'),
    },
    stopping: {
      color: 'var(--text-tertiary)',
      icon: <BadgeSpinner />,
      label: t('world.session.stopping'),
    },
  }
  const cfg = configs[state] ?? configs.idle
  return (
    <span
      role="status"
      aria-label={cfg.label}
      className="inline-flex items-center gap-[5px] text-[12px] font-medium whitespace-nowrap"
      style={{ color: cfg.color }}
    >
      {cfg.icon}
      <span>{cfg.label}</span>
    </span>
  )
}

// ─── WorldSessionButton ───────────────────────────────────────────────────────
// Altura 28px, texto 12px (spec §8 — no saturar la celda de acciones).
function WorldSessionButton({ world, sessionState, onStart, onStop, onRetry, onEnter, t }) {
  const parsed = parseServerUrl(world.server) || world.server

  // Estilo base para botones de sesión pequeños
  const base = 'h-7 px-[10px] rounded-[var(--radius-sm)] text-[12px] font-medium font-[inherit] whitespace-nowrap cursor-pointer inline-flex items-center gap-[5px] flex-shrink-0 border transition-[background,opacity] duration-[var(--dur-fast)]'

  switch (sessionState) {
    case 'idle':
      return (
        <button
          type="button"
          onClick={() => onStart(world.id)}
          aria-label={t('world.session.start.aria').replace('{world}', parsed)}
          className={`${base} border-[var(--border-strong)] bg-[var(--surface)] text-[var(--text)] hover:bg-[var(--surface-2)]`}
        >
          {t('world.session.start')}
        </button>
      )
    case 'connecting':
      return (
        <button
          type="button"
          disabled
          className={`${base} border-[var(--border-strong)] bg-[var(--surface)] text-[var(--text)] opacity-50 cursor-not-allowed`}
        >
          <span style={{ width:'11px',height:'11px',border:'1.8px solid currentColor',borderTopColor:'transparent',borderRadius:'50%',display:'inline-block',flexShrink:0,animation:'spin 0.7s linear infinite' }} aria-hidden="true" />
          {t('world.session.cancel')}
        </button>
      )
    case 'active':
      return (
        <span className="inline-flex items-center gap-1">
          {/* Entrar — ghost-accent */}
          <button
            type="button"
            onClick={() => onEnter(world.id)}
            aria-label={t('world.session.enter.aria').replace('{world}', parsed)}
            className={`${base} border-[var(--accent-subtle)] bg-[var(--accent-subtle)] text-[var(--accent-text)] hover:bg-[rgba(138,100,24,.22)] hover:border-[var(--accent)]`}
            style={{ '--hover-bg': 'rgba(138,100,24,.22)' }}
          >
            {t('world.session.enter')}
          </button>
          {/* Parar — destructive */}
          <button
            type="button"
            onClick={() => onStop(world.id)}
            aria-label={t('world.session.stop.aria').replace('{world}', parsed)}
            className={`${base} border-[var(--danger)] bg-transparent text-[var(--danger)] hover:bg-[rgba(201,53,44,.06)]`}
          >
            {t('world.session.stop')}
          </button>
        </span>
      )
    case 'error':
      return (
        <button
          type="button"
          onClick={() => onRetry(world.id)}
          aria-label={t('world.session.retry.aria').replace('{world}', parsed)}
          className={`${base} border-[var(--border-strong)] bg-[var(--surface)] text-[var(--text)] hover:bg-[var(--surface-2)]`}
        >
          {t('world.session.retry')}
        </button>
      )
    case 'stopping':
      return null // Sin botón visible (spec §4b tabla)
    default:
      return null
  }
}

// ─── RowMenu — botón ⋯ + contexto ───────────────────────────────────────────
// IMPORTANTE: No envolver en overflow-hidden/auto — recorta el popover.
function RowMenu({ worldId, parsed, isBlocked, onDelete, t }) {
  const [open, setOpen]   = useState(false)
  const btnRef            = useRef(null)
  const menuRef           = useRef(null)

  useEffect(() => {
    if (!open) return
    function handler(e) {
      if (!menuRef.current?.contains(e.target) && !btnRef.current?.contains(e.target))
        setOpen(false)
    }
    function keyHandler(e) {
      if (e.key === 'Escape') { setOpen(false); btnRef.current?.focus() }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        menuRef.current?.querySelector('[role="menuitem"]')?.focus()
      }
    }
    document.addEventListener('mousedown', handler)
    document.addEventListener('keydown', keyHandler)
    return () => {
      document.removeEventListener('mousedown', handler)
      document.removeEventListener('keydown', keyHandler)
    }
  }, [open])

  // Foco al primer item al abrir
  useEffect(() => {
    if (open) {
      setTimeout(() => menuRef.current?.querySelector('[role="menuitem"]')?.focus(), 0)
    }
  }, [open])

  const tooltip = isBlocked
    ? t('world.session.disabled.delete')
    : `${t('page.account.action.deleteWorld')} ${parsed}`

  return (
    <div className="relative inline-flex" ref={menuRef}>
      <button
        ref={btnRef}
        type="button"
        disabled={isBlocked}
        title={tooltip}
        aria-label={tooltip}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={e => { e.stopPropagation(); if (!isBlocked) setOpen(v => !v) }}
        className="w-8 h-8 rounded-[var(--radius-sm)] border border-transparent
                   bg-transparent text-[var(--text-secondary)] grid place-items-center
                   cursor-pointer hover:bg-[var(--surface-2)] hover:border-[var(--border)]
                   hover:text-[var(--text)] disabled:opacity-45 disabled:cursor-not-allowed
                   flex-shrink-0"
      >
        <IconDots />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute end-0 top-[calc(100%+4px)] bg-[var(--surface)]
                     border border-[var(--border)] rounded-[var(--radius-md)]
                     shadow-[var(--shadow-lg)] p-[6px] min-w-[160px] z-[300]"
        >
          <button
            role="menuitem"
            type="button"
            onClick={() => { setOpen(false); onDelete() }}
            className="block w-full px-3 py-2 text-start text-[13px] text-[var(--danger)]
                       rounded-[var(--radius-sm)] cursor-pointer border-0 bg-transparent
                       font-[inherit] hover:bg-[var(--surface-2)]"
          >
            {t('page.account.action.deleteWorld')}
          </button>
        </div>
      )}
    </div>
  )
}

// ─── SkeletonRow ─────────────────────────────────────────────────────────────
function SkeletonRow() {
  return (
    <tr aria-hidden="true">
      <td className="px-[14px] h-10 border-b border-[var(--border)] hidden md:table-cell">
        <span className="block h-4 w-[180px] rounded bg-[var(--surface-2)]"
          style={{ animation: 'pulse 1.2s ease-in-out infinite' }} />
      </td>
      <td className="px-[14px] h-10 border-b border-[var(--border)]">
        <span className="block h-4 w-[140px] rounded bg-[var(--surface-2)]"
          style={{ animation: 'pulse 1.2s ease-in-out infinite' }} />
      </td>
      <td className="px-[14px] h-10 border-b border-[var(--border)]">
        <span className="block h-4 w-[70px] rounded bg-[var(--surface-2)]"
          style={{ animation: 'pulse 1.2s ease-in-out infinite' }} />
      </td>
      <td className="px-[14px] h-10 border-b border-[var(--border)]">
        <span className="block h-4 w-[100px] rounded bg-[var(--surface-2)]"
          style={{ animation: 'pulse 1.2s ease-in-out infinite' }} />
      </td>
      <td className="px-[14px] h-10 border-b border-[var(--border)] w-[160px]" />
    </tr>
  )
}

// ─── AccountDetailPage ────────────────────────────────────────────────────────

export function AccountDetailPage() {
  const { id }     = useParams()
  const navigate   = useNavigate()
  const { t, lang } = useI18n()

  // Detectar RTL para espejar flechas
  const isRTL = ['ar', 'he', 'fa'].includes(lang)

  // ── Estado principal ──────────────────────────────────────────────────────
  const [loadState, setLoadState] = useState('loading') // loading | ok | 404 | error
  const [account, setAccount]     = useState(null)  // AccountResponse
  const [worlds,  setWorlds]      = useState([])    // array de worlds

  // Estado de sesión por world id: Map<id, state>
  const [sessions, setSessions] = useState({})

  // Conteo de ataques por world id (Nivel 1 — badge).
  // Se puebla con GET /game/incoming-attacks/summary (una sola petición).
  // Si el fetch falla: {} → sin badges (fallo silencioso, spec §7.1).
  const [attackCounts, setAttackCounts] = useState({})

  // ── Modales ───────────────────────────────────────────────────────────────
  const [showAddWorld,setShowAddWorld]= useState(false)
  const [deleteWorld, setDeleteWorld] = useState(null) // { id, parsed } | null

  // refs para devolver foco al trigger que abrió cada modal
  const addWorldBtnRef    = useRef(null)
  const deleteWorldBtnRef = useRef(null)

  // ── Carga inicial ─────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoadState('loading')
      try {
        const data = await api.getAccount(id)
        if (cancelled) return
        setAccount(data)
        const w = data.worlds ?? []
        setWorlds(w)
        // Inicializar todos los mundos como idle
        const initialSessions = {}
        w.forEach(world => { initialSessions[world.id] = 'idle' })
        setSessions(initialSessions)
        setLoadState('ok')
        // Consultar el estado de sesión de cada mundo (silencioso: 404/501 → idle)
        w.forEach(world => fetchSessionState(data.id, world.id))
        // Consultar ataques entrantes de todos los mundos (Nivel 1 — una sola petición)
        fetchAttacksSummary()
      } catch (err) {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 404) {
          setLoadState('404')
        } else {
          setLoadState('error')
          showToast(t('error.network'))
        }
      }
    }
    load()
    return () => { cancelled = true }
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Consulta de estado de sesión (silenciosa) ─────────────────────────────
  async function fetchSessionState(accountId, worldId) {
    try {
      const data = await api.getSession(accountId, worldId)
      // El backend devuelve { active: bool } según el spec §4b
      setSession(worldId, data?.active ? 'active' : 'idle')
    } catch {
      // 404/501/cualquier error → dejar como idle (no romper la UI)
    }
  }

  // ── Consulta de ataques entrantes — Nivel 1 (silenciosa) ─────────────────
  // Una sola petición para todos los mundos con sesión activa.
  // Si falla → {} → sin badges. No degrada la UI de la fila (spec §5.5, §7.1).
  async function fetchAttacksSummary() {
    try {
      const summary = await api.getIncomingAttacksSummary()
      if (!Array.isArray(summary)) return
      const map = {}
      summary.forEach(item => {
        if (item.attack_count > 0) {
          map[item.world_id] = item.attack_count
        }
      })
      setAttackCounts(map)
    } catch {
      // Fallo silencioso: sin badges (spec §7.1 "Error de fetch")
    }
  }

  function setSession(worldId, state) {
    setSessions(prev => ({ ...prev, [worldId]: state }))
  }

  // ── Acciones de sesión ────────────────────────────────────────────────────

  async function handleStart(worldId) {
    const parsed = parseServerUrl(worlds.find(w => w.id === worldId)?.server ?? '') || worldId
    setSession(worldId, 'connecting')
    try {
      await api.startSession(account.id, worldId)
      setSession(worldId, 'active')
      showToast(t('world.session.started.toast').replace('{world}', parsed))
      // Navegar al Espacio del mundo (spec §8: solo tras 200 OK)
      navigate(`/mundos/${worldId}`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setSession(worldId, 'error')
        showToast(t('world.session.error.toast').replace('{world}', parsed))
      } else {
        setSession(worldId, 'error')
        showToast(t('error.network'))
      }
    }
  }

  async function handleStop(worldId) {
    const parsed = parseServerUrl(worlds.find(w => w.id === worldId)?.server ?? '') || worldId
    setSession(worldId, 'stopping')
    try {
      await api.stopSession(account.id, worldId)
      setSession(worldId, 'idle')
      showToast(t('world.session.stopped.toast').replace('{world}', parsed))
    } catch {
      // Revertir a activo si falla
      setSession(worldId, 'active')
      showToast(t('error.network'))
    }
  }

  function handleRetry(worldId) {
    handleStart(worldId)
  }

  function handleEnter(worldId) {
    navigate(`/mundos/${worldId}`)
  }

  // ── Borrar mundo ──────────────────────────────────────────────────────────
  async function handleDeleteWorld() {
    if (!deleteWorld) return
    await api.deleteWorld(account.id, deleteWorld.id)
    showToast(t('modal.deleteWorld.toast'))
    setWorlds(prev => prev.filter(w => w.id !== deleteWorld.id))
    setSessions(prev => {
      const next = { ...prev }
      delete next[deleteWorld.id]
      return next
    })
    setDeleteWorld(null)
  }

  // ── Callback al añadir mundo con éxito ────────────────────────────────────
  function handleWorldAdded(newWorld) {
    if (newWorld) {
      setWorlds(prev => [...prev, newWorld])
      setSessions(prev => ({ ...prev, [newWorld.id]: 'idle' }))
    } else {
      // Recargar si el backend no devuelve el recurso
      api.getAccount(id).then(data => {
        setAccount(data)
        const w = data.worlds ?? []
        setWorlds(w)
        setSessions(prev => {
          const next = { ...prev }
          w.forEach(world => { if (!next[world.id]) next[world.id] = 'idle' })
          return next
        })
      }).catch(() => {})
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────

  // ── Estado: cargando ──────────────────────────────────────────────────────
  if (loadState === 'loading') {
    return (
      <div className="p-6 lg:p-8" aria-busy="true">
        {/* Skeleton breadcrumb */}
        <div className="mb-5">
          <span className="block h-4 w-20 rounded bg-[var(--surface-2)]"
            style={{ animation: 'pulse 1.2s ease-in-out infinite' }} aria-hidden="true" />
        </div>
        {/* Skeleton tabla */}
        <div className="mb-3" aria-hidden="true">
          <span className="block h-5 w-28 rounded bg-[var(--surface-2)]"
            style={{ animation: 'pulse 1.2s ease-in-out infinite' }} />
        </div>
        <table className="w-full border-collapse" aria-hidden="true">
          <thead>
            <tr>
              <th className="hidden md:table-cell h-[34px] px-[14px] bg-[var(--surface-2)] border-b border-[var(--border)] text-start" />
              <th className="h-[34px] px-[14px] bg-[var(--surface-2)] border-b border-[var(--border)] text-start" />
              <th className="h-[34px] px-[14px] bg-[var(--surface-2)] border-b border-[var(--border)] text-start" />
              <th className="h-[34px] px-[14px] bg-[var(--surface-2)] border-b border-[var(--border)] text-start" />
              <th className="h-[34px] px-[14px] bg-[var(--surface-2)] border-b border-[var(--border)] w-[160px]" />
            </tr>
          </thead>
          <tbody>
            <SkeletonRow /><SkeletonRow /><SkeletonRow />
          </tbody>
        </table>
      </div>
    )
  }

  // ── Estado: 404 ───────────────────────────────────────────────────────────
  if (loadState === '404') {
    return (
      <div className="p-6 lg:p-8">
        <nav aria-label="Migas de pan" className="mb-0">
          <Link
            to="/cuentas"
            className="inline-flex items-center gap-1 text-[var(--accent-text)] hover:text-[var(--accent-hover)] text-[13px]"
          >
            <ArrowBack isRTL={isRTL} />
            {t('page.account.breadcrumb')}
          </Link>
        </nav>
        <div className="flex flex-col items-center justify-center gap-[14px] py-20 text-center">
          <div className="w-14 h-14 rounded-full bg-[var(--surface-2)] grid place-items-center text-[var(--text-tertiary)]">
            <IconWarning />
          </div>
          <h2 className="text-[20px] font-semibold tracking-[-0.01em] text-[var(--text)]">
            {t('page.account.notFound.title')}
          </h2>
          <p className="text-[14px] text-[var(--text-secondary)] max-w-xs leading-[1.5]">
            {t('page.account.notFound.desc')}
          </p>
          <Link
            to="/cuentas"
            className="h-8 px-[14px] rounded-[var(--radius-sm)] border-0 inline-flex items-center
                       bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)]
                       text-[13px] font-medium hover:bg-[var(--btn-primary-hover)]"
          >
            {t('page.account.notFound.back')}
          </Link>
        </div>
      </div>
    )
  }

  // ── Estado: error de red (toast ya mostrado en la carga) ──────────────────
  if (loadState === 'error') {
    return (
      <div className="p-6 lg:p-8">
        <nav aria-label="Migas de pan">
          <Link
            to="/cuentas"
            className="inline-flex items-center gap-1 text-[var(--accent-text)] hover:text-[var(--accent-hover)] text-[13px]"
          >
            <ArrowBack isRTL={isRTL} />
            {t('page.account.breadcrumb')}
          </Link>
        </nav>
        <p className="text-[14px] text-[var(--text-secondary)] mt-6">{t('error.loadFailed')}</p>
      </div>
    )
  }

  // ── Estado: datos cargados (ok) ───────────────────────────────────────────
  const worldCount = worlds.length

  return (
    <div className="p-6 lg:p-8">

      {/* Breadcrumb */}
      <nav aria-label="Migas de pan" className="mb-5">
        <div className="flex items-center gap-[6px] text-[13px] text-[var(--text-secondary)]">
          <Link
            to="/cuentas"
            className="inline-flex items-center gap-1 text-[var(--accent-text)] hover:text-[var(--accent-hover)]"
          >
            <ArrowBack isRTL={isRTL} />
            {t('page.account.breadcrumb')}
          </Link>
          <span className="text-[var(--text-tertiary)]">/</span>
          <span className="text-[var(--text-secondary)]">{account?.username}</span>
        </div>
      </nav>

      {/* Sección mundos */}
      <div>
        {/* Sub-header mundos. flex-wrap para que el botón baje de línea en
            idiomas largos (griego, alemán…) en vez de desbordar la pantalla. */}
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-2 mb-3">
          <h3 className="text-[17px] font-semibold tracking-[-0.01em] text-[var(--text)]">
            {t('page.account.worlds.title', { n: worldCount })}
          </h3>
          <span className="flex-1" />
          <button
            ref={addWorldBtnRef}
            type="button"
            onClick={() => setShowAddWorld(true)}
            className="h-[30px] px-[12px] rounded-[var(--radius-sm)] border border-[var(--border-strong)]
                       bg-[var(--surface)] text-[var(--text)] text-[13px] font-[inherit]
                       cursor-pointer inline-flex items-center gap-[5px] whitespace-nowrap
                       hover:bg-[var(--surface-2)]"
          >
            <IconPlus />
            {t('page.account.worlds.add')}
          </button>
        </div>

        {/* Empty state mundos */}
        {worldCount === 0 && (
          <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
            <div className="w-[52px] h-[52px] rounded-full bg-[var(--surface-2)]
                            grid place-items-center text-[var(--text-tertiary)]">
              <IconGlobe />
            </div>
            <p className="text-[14px] text-[var(--text-secondary)] leading-[1.5]">
              {t('page.account.worlds.empty')}
            </p>
            <button
              type="button"
              onClick={() => setShowAddWorld(true)}
              className="text-[13px] text-[var(--accent-text)] hover:text-[var(--accent-hover)]
                         bg-transparent border-0 cursor-pointer font-[inherit]"
            >
              {t('page.account.worlds.add')}
            </button>
          </div>
        )}

        {/* Tabla desktop (≥ md) */}
        {worldCount > 0 && (
          <>
            <div className="hidden md:block">
              <table className="w-full border-collapse text-[14px]" role="table">
                <thead>
                  <tr>
                    <th className="bg-[var(--surface-2)] text-[var(--text-secondary)] text-[11px] font-medium
                                   uppercase tracking-[0.04em] px-[14px] h-[34px] text-start
                                   border-b border-[var(--border)] whitespace-nowrap hidden md:table-cell"
                      role="columnheader">
                      {t('page.account.col.server')}
                    </th>
                    <th className="bg-[var(--surface-2)] text-[var(--text-secondary)] text-[11px] font-medium
                                   uppercase tracking-[0.04em] px-[14px] h-[34px] text-start
                                   border-b border-[var(--border)] whitespace-nowrap"
                      role="columnheader">
                      {t('page.account.col.parsed')}
                    </th>
                    <th className="bg-[var(--surface-2)] text-[var(--text-secondary)] text-[11px] font-medium
                                   uppercase tracking-[0.04em] px-[14px] h-[34px] text-start
                                   border-b border-[var(--border)] whitespace-nowrap"
                      role="columnheader">
                      {t('page.account.col.tribe')}
                    </th>
                    <th className="bg-[var(--surface-2)] text-[var(--text-secondary)] text-[11px] font-medium
                                   uppercase tracking-[0.04em] px-[14px] h-[34px] text-start
                                   border-b border-[var(--border)] whitespace-nowrap min-w-[130px]"
                      role="columnheader">
                      {t('page.account.col.session')}
                    </th>
                    <th className="bg-[var(--surface-2)] border-b border-[var(--border)] w-[160px]"
                      role="columnheader" aria-label={t('page.account.col.actions')} />
                  </tr>
                </thead>
                <tbody>
                  {worlds.map(world => {
                    const parsed    = parseServerUrl(world.server) || world.server
                    const state     = sessions[world.id] ?? 'idle'
                    const isBlocked = ['active','connecting','stopping'].includes(state)
                    return (
                      <tr key={world.id} role="row">
                        {/* URL completa — P2, oculta en < md */}
                        <td
                          className="px-[14px] h-10 border-b border-[var(--border)] align-middle
                                     hidden md:table-cell font-mono text-[12px]
                                     max-w-[200px] overflow-hidden text-ellipsis whitespace-nowrap"
                          role="cell"
                        >
                          {state === 'active' ? (
                            <button
                              type="button"
                              onClick={() => handleEnter(world.id)}
                              title={t('page.account.enterWorld')}
                              className="text-[var(--accent-text)] font-mono text-[12px] bg-transparent border-0 p-0 cursor-pointer font-[inherit] underline underline-offset-2 truncate max-w-[200px] block"
                            >
                              {world.server}
                            </button>
                          ) : (
                            <span className="text-[var(--text-secondary)]">{world.server}</span>
                          )}
                        </td>
                        {/* Vista parsada — P1 */}
                        <td className="px-[14px] h-10 border-b border-[var(--border)] align-middle
                                       font-mono text-[13px] text-[var(--accent-text)]"
                          role="cell">
                          {parsed}
                        </td>
                        {/* Tribu */}
                        <td className="px-[14px] h-10 border-b border-[var(--border)] align-middle capitalize"
                          role="cell">
                          {t(`tribe.${world.tribe}`)}
                        </td>
                        {/* Sesión — SessionStatusBadge + AttackBadge (Nivel 1, P1) */}
                        <td className="px-[14px] h-10 border-b border-[var(--border)] align-middle whitespace-nowrap"
                          role="cell">
                          <span className="inline-flex items-center gap-[8px]">
                            <SessionStatusBadge state={state} t={t} />
                            {/* AttackBadge solo cuando hay sesión activa (spec §7.1) */}
                            {state === 'active' && (
                              <AttackBadge count={attackCounts[world.id] ?? 0} t={t} />
                            )}
                          </span>
                        </td>
                        {/* Acciones */}
                        <td className="px-[14px] h-10 border-b border-[var(--border)] align-middle w-[160px]"
                          role="cell">
                          <div className="flex items-center justify-end gap-1">
                            <WorldSessionButton
                              world={world}
                              sessionState={state}
                              onStart={handleStart}
                              onStop={handleStop}
                              onRetry={handleRetry}
                              onEnter={handleEnter}
                              t={t}
                            />
                            <RowMenu
                              worldId={world.id}
                              parsed={parsed}
                              isBlocked={isBlocked}
                              t={t}
                              onDelete={() => {
                                setDeleteWorld({ id: world.id, parsed })
                              }}
                            />
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Tarjetas móvil (< md) */}
            <div className="md:hidden flex flex-col gap-2">
              {worlds.map(world => {
                const parsed    = parseServerUrl(world.server) || world.server
                const state     = sessions[world.id] ?? 'idle'
                const isBlocked = ['active','connecting','stopping'].includes(state)
                return (
                  <div
                    key={world.id}
                    className="bg-[var(--surface)] border border-[var(--border)]
                               rounded-[var(--radius-md)] p-[14px_16px]
                               flex items-center gap-3"
                  >
                    <div className="flex-1 min-w-0">
                      {state === 'active' ? (
                        <button
                          type="button"
                          onClick={() => handleEnter(world.id)}
                          title={t('page.account.enterWorld')}
                          className="font-semibold text-[14px] text-[var(--accent-text)] font-mono truncate bg-transparent border-0 p-0 cursor-pointer font-[inherit] underline underline-offset-2 text-left w-full"
                        >
                          {parsed}
                        </button>
                      ) : (
                        <div className="font-semibold text-[14px] text-[var(--accent-text)] font-mono truncate">
                          {parsed}
                        </div>
                      )}
                      <div className="text-[12px] text-[var(--text-secondary)] mt-[2px]">
                        {t(`tribe.${world.tribe}`)}
                      </div>
                      {/* Línea secundaria: tribu · • Activo  ⚔ N (spec §6.1 móvil, P1) */}
                      <div className="mt-[6px] flex items-center gap-[8px]">
                        <SessionStatusBadge state={state} t={t} />
                        {/* AttackBadge solo cuando hay sesión activa (spec §7.1) */}
                        {state === 'active' && (
                          <AttackBadge count={attackCounts[world.id] ?? 0} t={t} />
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <WorldSessionButton
                        world={world}
                        sessionState={state}
                        onStart={handleStart}
                        onStop={handleStop}
                        onRetry={handleRetry}
                        onEnter={handleEnter}
                        t={t}
                      />
                      <RowMenu
                        worldId={world.id}
                        parsed={parsed}
                        isBlocked={isBlocked}
                        t={t}
                        onDelete={() => setDeleteWorld({ id: world.id, parsed })}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>

      {/* ── Modales ─────────────────────────────────────────────────────── */}

      {/* S6 — Añadir mundo */}
      {showAddWorld && (
        <AddWorldModal
          accountId={account.id}
          onClose={() => setShowAddWorld(false)}
          onAdded={handleWorldAdded}
          triggerRef={addWorldBtnRef}
        />
      )}

      {/* S8 — Confirmar borrado de mundo */}
      {deleteWorld && (
        <ConfirmDeleteModal
          title={t('modal.deleteWorld.title')}
          question={t('modal.deleteWorld.body', { parsed: deleteWorld.parsed })}
          warning={t('modal.deleteWorld.warning')}
          onConfirm={handleDeleteWorld}
          onClose={() => setDeleteWorld(null)}
          triggerRef={deleteWorldBtnRef}
        />
      )}
    </div>
  )
}
