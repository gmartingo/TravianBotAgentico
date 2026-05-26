/**
 * AccountsListPage — S2 Lista de cuentas.
 *
 * Implementa el mockup aprobado en frontend/mockups/cuentas.playground.html.
 * Cuatro estados estilados: loading (skeleton), data (tabla/tarjetas), empty, error.
 *
 * Responsive (DESIGN.md §17):
 *   ≥ md (768px): tabla con columnas Email / Usuario / Mundos / Creada / Acciones.
 *   < md: tarjetas apiladas (AccountCard).
 *   Columna "Creada" (P3) oculta en < lg (1024px).
 *
 * Accesibilidad: roles ARIA, navegación por teclado en filas y tarjetas,
 *   orden de foco coherente, foco visible (via app.css :focus-visible).
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useI18n } from '../i18n/index.jsx'
import { api } from '../api/client.js'
import { EditAccountModal } from '../components/ui/EditAccountModal.jsx'

// ─── Iconos inline SVG (Lucide-style, línea fina 1.8px) ─────────────────────

function IconUser({ size = 28 }) {
  return (
    <svg
      width={size} height={size}
      viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  )
}

function IconPlus({ size = 14 }) {
  return (
    <svg
      width={size} height={size}
      viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function IconAlert({ size = 16 }) {
  return (
    <svg
      width={size} height={size}
      viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  )
}

// ─── Skeleton de carga ───────────────────────────────────────────────────────

function SkeletonCell({ width }) {
  return (
    <span
      className="skeleton-pulse inline-block h-4 rounded bg-[var(--surface-2)]"
      style={{ width }}
      aria-hidden="true"
    />
  )
}

function SkeletonRows() {
  const widths = [
    ['180px', '100px', '24px', '80px'],
    ['160px', '90px',  '24px', '80px'],
    ['200px', '120px', '24px', '80px'],
  ]
  return (
    <>
      {widths.map((row, i) => (
        <tr key={i} aria-hidden="true">
          <td className="px-[14px] py-[10px] border-b border-[var(--border)]">
            <SkeletonCell width={row[0]} />
          </td>
          <td className="px-[14px] py-[10px] border-b border-[var(--border)]">
            <SkeletonCell width={row[1]} />
          </td>
          <td className="px-[14px] py-[10px] border-b border-[var(--border)] text-end">
            <SkeletonCell width={row[2]} />
          </td>
          <td className="px-[14px] py-[10px] border-b border-[var(--border)] hidden lg:table-cell">
            <SkeletonCell width={row[3]} />
          </td>
          <td className="px-[14px] py-[10px] border-b border-[var(--border)] w-[48px]" />
        </tr>
      ))}
    </>
  )
}

// ─── Tabla de cabeceras (reutilizada en varios estados) ─────────────────────

function TableHead({ t }) {
  return (
    <thead>
      <tr>
        <th className="bg-[var(--surface-2)] text-[var(--text-secondary)] text-[11px] font-medium uppercase tracking-[0.04em] px-[14px] h-[34px] text-start border-b border-[var(--border)] whitespace-nowrap">
          {t('page.accounts.col.email')}
        </th>
        <th className="bg-[var(--surface-2)] text-[var(--text-secondary)] text-[11px] font-medium uppercase tracking-[0.04em] px-[14px] h-[34px] text-start border-b border-[var(--border)] whitespace-nowrap">
          {t('page.accounts.col.username')}
        </th>
        <th className="bg-[var(--surface-2)] text-[var(--text-secondary)] text-[11px] font-medium uppercase tracking-[0.04em] px-[14px] h-[34px] text-end border-b border-[var(--border)] whitespace-nowrap">
          {t('page.accounts.col.worlds')}
        </th>
        <th className="bg-[var(--surface-2)] text-[var(--text-secondary)] text-[11px] font-medium uppercase tracking-[0.04em] px-[14px] h-[34px] text-start border-b border-[var(--border)] whitespace-nowrap hidden lg:table-cell">
          {t('page.accounts.col.created')}
        </th>
        <th className="bg-[var(--surface-2)] border-b border-[var(--border)] w-[48px]" />
      </tr>
    </thead>
  )
}

// ─── Menú contextual de fila ─────────────────────────────────────────────────

function RowMenu({ account, onEdit, onDelete, t }) {
  const [open, setOpen] = useState(false)
  const menuRef = useRef(null)
  const btnRef  = useRef(null)

  // Cerrar al hacer clic fuera
  useEffect(() => {
    if (!open) return
    function handler(e) {
      if (!menuRef.current?.contains(e.target) && !btnRef.current?.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Cerrar con Escape
  useEffect(() => {
    if (!open) return
    function handler(e) {
      if (e.key === 'Escape') { setOpen(false); btnRef.current?.focus() }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open])

  return (
    <div className="relative inline-block">
      <button
        ref={btnRef}
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen(v => !v) }}
        aria-label={account.username}
        aria-haspopup="true"
        aria-expanded={open}
        className="w-8 h-8 rounded-[var(--radius-sm)] grid place-items-center
                   text-[var(--text-secondary)] border border-transparent bg-transparent
                   hover:bg-[var(--surface-2)] hover:border-[var(--border)] hover:text-[var(--text)]
                   transition-colors duration-[var(--dur-fast)] cursor-pointer text-[16px]"
      >
        ⋯
      </button>

      {open && (
        <div
          ref={menuRef}
          role="menu"
          className="absolute end-0 top-[calc(100%+4px)] min-w-[160px] z-[300]
                     bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-md)]
                     shadow-[var(--shadow-lg)] py-1.5"
        >
          <button
            type="button"
            role="menuitem"
            onClick={(e) => { e.stopPropagation(); setOpen(false); onEdit(account) }}
            className="block w-full px-3 py-2 text-start font-[inherit] text-[13px]
                       text-[var(--text)] bg-transparent border-none
                       rounded-[var(--radius-sm)] cursor-pointer
                       hover:bg-[var(--surface-2)]"
          >
            {t('page.accounts.action.edit')}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={(e) => { e.stopPropagation(); setOpen(false); onDelete(account) }}
            className="block w-full px-3 py-2 text-start font-[inherit] text-[13px]
                       text-[var(--danger)] bg-transparent border-none
                       rounded-[var(--radius-sm)] cursor-pointer
                       hover:bg-[var(--surface-2)]"
          >
            {t('page.accounts.action.delete')}
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Fila de la tabla ────────────────────────────────────────────────────────

function AccountRow({ account, onNavigate, onEdit, onDelete, t, lang }) {
  function fmtDate(dateStr) {
    if (!dateStr) return '—'
    try {
      const d = new Date(dateStr)
      return new Intl.DateTimeFormat(lang, {
        day: 'numeric', month: 'short', year: 'numeric',
      }).format(d)
    } catch {
      return dateStr
    }
  }

  function handleRowClick(e) {
    // No navegar si el clic vino del botón de menú
    if (e.target.closest('[role="menu"]') || e.target.closest('button')) return
    onNavigate(account.id)
  }

  function handleRowKeyDown(e) {
    if ((e.key === 'Enter' || e.key === ' ') && !e.target.closest('button')) {
      e.preventDefault()
      onNavigate(account.id)
    }
  }

  return (
    <tr
      role="row"
      tabIndex={0}
      aria-label={account.username}
      onClick={handleRowClick}
      onKeyDown={handleRowKeyDown}
      className="cursor-pointer transition-colors duration-[var(--dur-fast)]
                 hover:[&>td]:bg-[var(--surface-2)]"
    >
      <td className="px-[14px] h-[40px] border-b border-[var(--border)] font-medium text-[var(--text)] align-middle">
        {account.email}
      </td>
      <td className="px-[14px] h-[40px] border-b border-[var(--border)] text-[var(--text)] align-middle">
        {account.username}
      </td>
      <td className="px-[14px] h-[40px] border-b border-[var(--border)] text-end font-mono tabular-nums text-[var(--text)] align-middle">
        {account.worlds?.length ?? 0}
      </td>
      <td className="px-[14px] h-[40px] border-b border-[var(--border)] text-[var(--text-secondary)] text-[13px] align-middle hidden lg:table-cell">
        {fmtDate(account.created_at)}
      </td>
      <td className="px-[14px] h-[40px] border-b border-[var(--border)] w-[48px] text-end align-middle">
        <RowMenu account={account} onEdit={onEdit} onDelete={onDelete} t={t} />
      </td>
    </tr>
  )
}

// ─── Tarjeta móvil ───────────────────────────────────────────────────────────

function AccountCard({ account, onNavigate, onEdit, onDelete, t }) {
  function handleClick(e) {
    if (e.target.closest('button')) return
    onNavigate(account.id)
  }

  function handleKeyDown(e) {
    if ((e.key === 'Enter' || e.key === ' ') && !e.target.closest('button')) {
      e.preventDefault()
      onNavigate(account.id)
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={account.username}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className="bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-md)]
                 px-4 py-3.5 mb-2.5 flex items-center gap-3 cursor-pointer
                 transition-colors duration-[var(--dur-fast)] hover:bg-[var(--surface-2)]"
    >
      <div className="flex-1 min-w-0">
        <div className="font-medium text-[14px] text-[var(--text)] whitespace-nowrap overflow-hidden text-ellipsis">
          {account.email}
        </div>
        <div className="text-[12px] text-[var(--text-secondary)] mt-0.5">
          {account.username}&nbsp;&middot;&nbsp;
          {account.worlds?.length ?? 0}&nbsp;{t('page.accounts.col.worlds').toLowerCase()}
        </div>
      </div>
      <RowMenu account={account} onEdit={onEdit} onDelete={onDelete} t={t} />
    </div>
  )
}

// ─── Estado: CON DATOS ───────────────────────────────────────────────────────

function StateData({ accounts, onNavigate, onEdit, onDelete, t, lang }) {
  return (
    <>
      {/* Tabla — visible en md+. SIN overflow-x-auto: recortaba el desplegable
          del menú ⋯ (overflow crea contexto de recorte). La tabla cabe en ≥768px;
          en <768px se usan tarjetas. */}
      <div className="hidden md:block">
        <table
          className="w-full border-collapse text-[14px]"
          role="table"
          aria-label={t('page.accounts.title')}
        >
          <TableHead t={t} />
          <tbody>
            {accounts.map(account => (
              <AccountRow
                key={account.id}
                account={account}
                onNavigate={onNavigate}
                onEdit={onEdit}
                onDelete={onDelete}
                t={t}
                lang={lang}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Tarjetas — visible en < md */}
      <div className="md:hidden">
        {accounts.map(account => (
          <AccountCard
            key={account.id}
            account={account}
            onNavigate={onNavigate}
            onEdit={onEdit}
            onDelete={onDelete}
            t={t}
          />
        ))}
      </div>
    </>
  )
}

// ─── Estado: CARGANDO (skeleton) ─────────────────────────────────────────────

function StateLoading({ t }) {
  return (
    <div aria-busy="true" aria-label={t('page.accounts.loading')}>
      {/* Skeleton tabla — visible en md+ */}
      <div className="hidden md:block">
        <table className="w-full border-collapse text-[14px]" role="table">
          <TableHead t={t} />
          <tbody>
            <SkeletonRows />
          </tbody>
        </table>
      </div>

      {/* Skeleton tarjetas — visible en < md */}
      <div className="md:hidden space-y-2.5">
        {[180, 160, 200].map((w, i) => (
          <div
            key={i}
            aria-hidden="true"
            className="bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-md)] px-4 py-3.5 flex items-center gap-3"
          >
            <div className="flex-1 space-y-2">
              <span className="skeleton-pulse block h-4 rounded bg-[var(--surface-2)]" style={{ width: w }} />
              <span className="skeleton-pulse block h-3 rounded bg-[var(--surface-2)]" style={{ width: Math.round(w * 0.6) }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Estado: VACÍO ───────────────────────────────────────────────────────────

function StateEmpty({ onNewAccount, t }) {
  return (
    <>
      {/* Mantener cabecera de tabla para consistencia visual en md+ */}
      <div className="hidden md:block">
        <table className="w-full border-collapse text-[14px]" role="table">
          <TableHead t={t} />
        </table>
      </div>

      <div className="flex flex-col items-center justify-center gap-3 py-16 px-6 text-center">
        <div
          className="w-[52px] h-[52px] rounded-[var(--radius-full)] bg-[var(--surface-2)]
                     grid place-items-center text-[var(--text-tertiary)]"
          aria-hidden="true"
        >
          <IconUser size={28} />
        </div>
        <p className="text-[16px] font-semibold text-[var(--text)]">
          {t('page.accounts.empty.title')}
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] max-w-[300px] leading-[1.5]">
          {t('page.accounts.empty.desc')}
        </p>
        <button
          type="button"
          onClick={onNewAccount}
          className="mt-1 flex items-center gap-1.5 h-8 px-[14px] rounded-[var(--radius-sm)]
                     bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)]
                     text-[13px] font-medium border-none cursor-pointer whitespace-nowrap
                     hover:bg-[var(--btn-primary-hover)] transition-colors duration-[var(--dur-fast)]"
        >
          <IconPlus />
          {t('page.accounts.newAccount')}
        </button>
      </div>
    </>
  )
}

// ─── Estado: ERROR ───────────────────────────────────────────────────────────

function StateError({ onRetry, t }) {
  return (
    <>
      <div className="hidden md:block">
        <table className="w-full border-collapse text-[14px]" role="table">
          <TableHead t={t} />
        </table>
      </div>
    </>
  )
}

// ─── Banner de error (se muestra encima del contenido) ───────────────────────

function ErrorBanner({ onRetry, t }) {
  return (
    <div
      role="alert"
      className="flex items-center gap-2.5 px-[14px] py-3 mb-5
                 border border-[var(--danger)]
                 rounded-[var(--radius-sm)] text-[13px]"
      style={{ background: 'color-mix(in srgb, var(--danger) 10%, transparent)' }}
    >
      <IconAlert />
      <span className="flex-1 text-[var(--text)]">
        {t('error.loadFailed')}
      </span>
      <button
        type="button"
        onClick={onRetry}
        className="bg-transparent border-none text-[var(--accent-text)] font-[inherit]
                   text-[13px] cursor-pointer p-0 underline
                   hover:text-[var(--accent-hover)]"
      >
        {t('error.retry')}
      </button>
    </div>
  )
}

// ─── Modal de confirmación de borrado ────────────────────────────────────────

function DeleteConfirmModal({ account, onConfirm, onCancel, t }) {
  // Foco al abrir
  const confirmBtnRef = useRef(null)
  useEffect(() => {
    confirmBtnRef.current?.focus()
  }, [])

  // Cerrar con Escape
  useEffect(() => {
    function handler(e) {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onCancel])

  return (
    <div
      className="fixed inset-0 z-[400] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-modal-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30"
        onClick={onCancel}
        aria-hidden="true"
      />
      {/* Panel */}
      <div className="relative bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)] p-6 w-full max-w-[400px]">
        <h2
          id="delete-modal-title"
          className="text-[17px] font-semibold text-[var(--text)] mb-3"
        >
          {t('modal.deleteAccount.title')}
        </h2>
        <p className="text-[14px] text-[var(--text)] mb-1">
          {t('modal.deleteAccount.body', { username: account.username })}
        </p>
        <p className="text-[13px] text-[var(--text-secondary)] mb-5 leading-[1.5]">
          {t('modal.deleteAccount.warning', { n: account.worlds?.length ?? 0 })}
        </p>
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="h-8 px-[14px] rounded-[var(--radius-sm)]
                       bg-[var(--surface)] border border-[var(--border-strong)]
                       text-[var(--text)] text-[13px] font-medium cursor-pointer
                       hover:bg-[var(--surface-2)] transition-colors duration-[var(--dur-fast)]"
          >
            {t('modal.deleteAccount.cancel')}
          </button>
          <button
            ref={confirmBtnRef}
            type="button"
            onClick={() => onConfirm(account)}
            className="h-8 px-[14px] rounded-[var(--radius-sm)]
                       bg-[var(--danger)] text-white text-[13px] font-medium
                       border-none cursor-pointer
                       hover:opacity-90 transition-opacity duration-[var(--dur-fast)]"
          >
            {t('modal.deleteAccount.confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Página principal ────────────────────────────────────────────────────────

export function AccountsListPage() {
  const { t, lang } = useI18n()
  const navigate = useNavigate()

  const [status, setStatus]     = useState('loading') // 'loading' | 'data' | 'empty' | 'error'
  const [accounts, setAccounts] = useState([])
  const [toDelete, setToDelete] = useState(null)       // account pendiente de borrar
  const [toEdit,   setToEdit]   = useState(null)       // account pendiente de editar
  const editTriggerRef          = useRef(null)          // foco al cerrar el modal

  const load = useCallback(async () => {
    setStatus('loading')
    try {
      const data = await api.getAccounts()
      if (Array.isArray(data) && data.length > 0) {
        setAccounts(data)
        setStatus('data')
      } else {
        setAccounts([])
        setStatus('empty')
      }
    } catch {
      setStatus('error')
    }
  }, [])

  useEffect(() => { load() }, [load])

  function handleNavigate(id) {
    navigate(`/cuentas/${id}`)
  }

  function handleNewAccount() {
    navigate('/cuentas/nueva')
  }

  async function handleDeleteConfirm(account) {
    setToDelete(null)
    try {
      await api.deleteAccount(account.id)
      // Recargar lista tras borrado
      await load()
    } catch {
      // El error se muestra al recargar; no interrumpimos el flujo aquí
    }
  }

  async function handleEditSaved() {
    // Recargar lista tras guardar cambios en la cuenta
    await load()
  }

  // Caption localizado con plural
  function caption() {
    if (status === 'loading') return ''
    if (status === 'error')   return ''
    const n = accounts.length
    return t('page.accounts.caption', { n })
  }

  return (
    <div className="px-4 py-7 lg:px-8 lg:py-7 max-w-[1400px]">

      {/* Banner de error (encima de la cabecera de página) */}
      {status === 'error' && (
        <ErrorBanner onRetry={load} t={t} />
      )}

      {/* Cabecera de página. flex-wrap: en idiomas con textos largos (griego, alemán…)
          el botón baja a otra línea en vez de desbordar la pantalla. */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2 mb-5">
        <h1 className="text-[28px] font-semibold tracking-[-0.02em] leading-[1.2] text-[var(--text)] md:text-[28px] text-[24px]">
          {t('page.accounts.title')}
        </h1>
        {caption() && (
          <span className="flex-1 text-[12px] text-[var(--text-secondary)]">
            {caption()}
          </span>
        )}
        <button
          type="button"
          disabled={status === 'loading'}
          onClick={handleNewAccount}
          aria-label={t('page.accounts.newAccount')}
          className="flex items-center gap-1.5 h-8 px-[14px] rounded-[var(--radius-sm)]
                     bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)]
                     text-[13px] font-medium border-none cursor-pointer whitespace-nowrap
                     hover:bg-[var(--btn-primary-hover)] transition-colors duration-[var(--dur-fast)]
                     disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <IconPlus />
          {t('page.accounts.newAccount')}
        </button>
      </div>

      {/* Cuerpo de la lista */}
      {status === 'loading' && <StateLoading t={t} />}

      {status === 'data' && (
        <StateData
          accounts={accounts}
          onNavigate={handleNavigate}
          onEdit={(account) => { setToEdit(account) }}
          onDelete={(account) => setToDelete(account)}
          t={t}
          lang={lang}
        />
      )}

      {status === 'empty' && (
        <StateEmpty onNewAccount={handleNewAccount} t={t} />
      )}

      {status === 'error' && <StateError onRetry={load} t={t} />}

      {/* Modal de edición de cuenta */}
      {toEdit && (
        <EditAccountModal
          account={toEdit}
          onClose={() => setToEdit(null)}
          onSaved={handleEditSaved}
          triggerRef={editTriggerRef}
        />
      )}

      {/* Modal de confirmación de borrado */}
      {toDelete && (
        <DeleteConfirmModal
          account={toDelete}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setToDelete(null)}
          t={t}
        />
      )}
    </div>
  )
}
