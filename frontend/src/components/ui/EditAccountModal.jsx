/**
 * EditAccountModal — S5 Modal editar cuenta.
 *
 * Spec: docs/design/gestion-cuentas-mundos.md §6 S5, §7 S5, §9 S5
 * Mockup: frontend/mockups/cuenta-detalle.playground.html (vista "Modal editar")
 *
 * - Campos Email y Username prefilled con los valores actuales.
 * - Contraseña oculta por defecto; enlace "Cambiar contraseña" la despliega.
 *   Una vez desplegada no se puede volver a ocultar (spec §5 Flujo 4).
 * - Si ambas contraseñas están visibles y tienen contenido, deben coincidir.
 * - PUT /accounts/:id → { email, username, password? } — sin password si no se cambió.
 * - 409 → error inline bajo email.
 * - Focus trap, ESC, foco devuelto al trigger al cerrar.
 * - CERO texto hardcodeado — todas las cadenas pasan por t().
 */
import { useState, useEffect, useRef } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api, ApiError } from '../../api/client.js'
import { Spinner, useFocusTrap, showToast } from './uiUtils.jsx'

// ─── Iconos ──────────────────────────────────────────────────────────────────

function IconEye({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function IconEyeOff({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  )
}

function IconLock({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

// ─── Estilos base de input ────────────────────────────────────────────────────
const inputBase = [
  'w-full h-9 border border-[var(--border-strong)] bg-[var(--surface)]',
  'text-[var(--text)] rounded-[var(--radius-sm)] px-[10px]',
  'text-[16px] md:text-[14px] font-[inherit]',   // 16px en móvil evita el auto-zoom de iOS
  'outline-none transition-[border-color] duration-[var(--dur-fast)]',
  'focus:border-[var(--accent)] focus:outline-2 focus:outline-[var(--accent)] focus:outline-offset-[1px]',
  'disabled:opacity-50 disabled:cursor-not-allowed',
  'placeholder:text-[var(--text-tertiary)]',
].join(' ')

const inputError = 'border-[var(--danger)] focus:outline-[var(--danger)]'

// ─── FormField ───────────────────────────────────────────────────────────────
function FormField({ label, required, error, children }) {
  return (
    <div className="flex flex-col gap-[5px] mb-4 last:mb-0">
      <label className="text-[12px] font-medium text-[var(--text-secondary)]">
        {label}
        {required && <span className="text-[var(--danger)] ms-[2px]" aria-hidden="true">*</span>}
      </label>
      {children}
      {error && (
        <span role="alert" className="text-[12px] text-[var(--danger)]">{error}</span>
      )}
    </div>
  )
}

// ─── EditAccountModal ────────────────────────────────────────────────────────

/**
 * @param {object} props
 * @param {object} props.account  — { id, email, username }
 * @param {Function} props.onClose — () => void
 * @param {Function} props.onSaved — (updatedAccount) => void
 * @param {React.RefObject} props.triggerRef — elemento que abrió el modal (para devolver foco)
 */
export function EditAccountModal({ account, onClose, onSaved, triggerRef }) {
  const { t } = useI18n()
  const modalRef = useRef(null)

  const [email,    setEmail]    = useState(account?.email    ?? '')
  const [username, setUsername] = useState(account?.username ?? '')
  const [emailErr, setEmailErr] = useState('')

  const [showPwFields, setShowPwFields]   = useState(false)
  const [newPw,        setNewPw]          = useState('')
  const [confirmPw,    setConfirmPw]      = useState('')
  const [showNewPw,    setShowNewPw]      = useState(false)
  const [showConfirmPw,setShowConfirmPw]  = useState(false)
  const [pwMismatch,   setPwMismatch]     = useState(false)

  const [saving, setSaving] = useState(false)

  useFocusTrap(modalRef, true)

  // Foco al primer campo al abrir
  useEffect(() => {
    const timer = setTimeout(() => {
      modalRef.current?.querySelector('input')?.focus()
    }, 50)
    return () => clearTimeout(timer)
  }, [])

  // ESC cierra (si no está guardando)
  useEffect(() => {
    function handler(e) {
      if (e.key === 'Escape' && !saving) handleClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [saving]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleClose() {
    onClose()
    triggerRef?.current?.focus()
  }

  function handleBackdropClick(e) {
    if (!saving && e.target === e.currentTarget) handleClose()
  }

  // Validar coincidencia de contraseñas
  function checkPwMismatch(p1, p2) {
    if (p1 && p2 && p1 !== p2) {
      setPwMismatch(true)
      return true
    }
    setPwMismatch(false)
    return false
  }

  // Guardar habilitado si:
  // - email y username no están vacíos
  // - si campos de pw visibles y tienen contenido, coinciden
  const pwVisible = showPwFields
  const pwHasContent = pwVisible && (newPw || confirmPw)
  const pwOk = !pwHasContent || (!pwMismatch && newPw === confirmPw && newPw.length > 0)
  const canSave = email.trim() && username.trim() && pwOk && !saving

  async function handleSave() {
    if (!canSave) return

    // Validar email básico
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setEmailErr(t('wizard.error.email.invalid'))
      return
    }
    setEmailErr('')

    const payload = { email: email.trim(), username: username.trim() }
    if (pwVisible && newPw) payload.password = newPw

    setSaving(true)
    try {
      const updated = await api.updateAccount(account.id, payload)
      showToast(t('modal.edit.savedToast'))
      onSaved(updated)
      handleClose()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setEmailErr(t('modal.edit.error409'))
      } else {
        showToast(t('error.network'))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-[400] flex items-center justify-center
                 bg-black/40 backdrop-blur-[2px]"
      style={{ animation: 'fadeIn var(--dur-slow) var(--ease)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="editModalTitle"
      onClick={handleBackdropClick}
    >
      {/* Modal */}
      <div
        ref={modalRef}
        className="bg-[var(--surface)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)]
                   flex flex-col max-h-[90vh]
                   w-[min(440px,92vw)]
                   max-sm:w-full max-sm:rounded-b-none max-sm:self-end"
        style={{ animation: 'slideUp var(--dur-slow) var(--ease)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-3 px-5 pt-[18px] pb-[14px]
                        border-b border-[var(--border)] flex-shrink-0">
          <span id="editModalTitle"
            className="text-[17px] font-semibold tracking-[-0.01em] text-[var(--text)]">
            {t('modal.edit.title')}
          </span>
          <button
            type="button"
            onClick={handleClose}
            aria-label={t('modal.edit.closeBtn')}
            className="w-7 h-7 rounded-[var(--radius-sm)] grid place-items-center
                       text-[var(--text-secondary)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]
                       text-[18px] leading-none flex-shrink-0 border-0 bg-transparent cursor-pointer"
          >
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="p-5 overflow-y-auto flex-1">
          {/* Email */}
          <FormField label={t('wizard.field.email')} required error={emailErr}>
            <input
              type="email"
              value={email}
              onChange={e => { setEmail(e.target.value); setEmailErr('') }}
              onBlur={() => {
                if (!email.trim()) setEmailErr(t('wizard.error.required'))
                else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
                  setEmailErr(t('wizard.error.email.invalid'))
              }}
              autoComplete="username"
              disabled={saving}
              className={`${inputBase} ${emailErr ? inputError : ''}`}
              aria-invalid={!!emailErr}
            />
          </FormField>

          {/* Username */}
          <FormField label={t('wizard.field.username')} required>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="off"
              disabled={saving}
              className={inputBase}
            />
          </FormField>

          {/* Separador */}
          <div className="h-px bg-[var(--border)] my-4" />

          {/* Cambiar contraseña — enlace o campos */}
          {!showPwFields ? (
            <button
              type="button"
              onClick={() => { setShowPwFields(true); setTimeout(() => modalRef.current?.querySelector('#editNewPw')?.focus(), 50) }}
              className="inline-flex items-center gap-[6px] text-[var(--accent-text)] text-[13px]
                         hover:text-[var(--accent-hover)] bg-transparent border-0 cursor-pointer p-0"
            >
              <IconLock />
              {t('modal.edit.changePassword')}
            </button>
          ) : (
            <div className="mt-3">
              {/* Contraseña nueva */}
              <FormField label={t('modal.edit.newPassword')}>
                <div className="relative flex items-center">
                  <input
                    id="editNewPw"
                    type={showNewPw ? 'text' : 'password'}
                    value={newPw}
                    onChange={e => { setNewPw(e.target.value); checkPwMismatch(e.target.value, confirmPw) }}
                    autoComplete="new-password"
                    placeholder="••••••••"
                    disabled={saving}
                    className={`${inputBase} pe-10 ${pwMismatch ? inputError : ''}`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPw(v => !v)}
                    className="absolute end-2 top-1/2 -translate-y-1/2 w-6 h-6
                               grid place-items-center text-[var(--text-secondary)]
                               hover:text-[var(--text)] border-0 bg-transparent cursor-pointer
                               rounded"
                    aria-label={showNewPw ? t('wizard.btn.hidePassword') : t('wizard.btn.showPassword')}
                  >
                    {showNewPw ? <IconEyeOff /> : <IconEye />}
                  </button>
                </div>
              </FormField>

              {/* Confirmar contraseña */}
              <FormField
                label={t('modal.edit.confirmPassword')}
                error={pwMismatch ? t('modal.edit.passwordMismatch') : ''}
              >
                <div className="relative flex items-center">
                  <input
                    type={showConfirmPw ? 'text' : 'password'}
                    value={confirmPw}
                    onChange={e => { setConfirmPw(e.target.value); checkPwMismatch(newPw, e.target.value) }}
                    autoComplete="new-password"
                    placeholder="••••••••"
                    disabled={saving}
                    className={`${inputBase} pe-10 ${pwMismatch ? inputError : ''}`}
                    aria-invalid={pwMismatch}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPw(v => !v)}
                    className="absolute end-2 top-1/2 -translate-y-1/2 w-6 h-6
                               grid place-items-center text-[var(--text-secondary)]
                               hover:text-[var(--text)] border-0 bg-transparent cursor-pointer
                               rounded"
                    aria-label={showConfirmPw ? t('wizard.btn.hidePassword') : t('wizard.btn.showPassword')}
                  >
                    {showConfirmPw ? <IconEyeOff /> : <IconEye />}
                  </button>
                </div>
              </FormField>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-[14px]
                        border-t border-[var(--border)] flex-shrink-0
                        max-sm:flex-col-reverse max-sm:items-stretch">
          <button
            type="button"
            onClick={handleClose}
            disabled={saving}
            className="h-8 px-[14px] rounded-[var(--radius-sm)] border border-[var(--border-strong)]
                       bg-[var(--surface)] text-[var(--text)] text-[13px] font-[inherit]
                       cursor-pointer inline-flex items-center gap-[6px] whitespace-nowrap
                       hover:bg-[var(--surface-2)] disabled:opacity-50 disabled:cursor-not-allowed
                       max-sm:w-full max-sm:justify-center"
          >
            {t('modal.edit.cancelBtn')}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            className="h-8 px-[14px] rounded-[var(--radius-sm)] border-0
                       bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)]
                       text-[13px] font-medium font-[inherit] cursor-pointer
                       inline-flex items-center gap-[6px] whitespace-nowrap
                       hover:bg-[var(--btn-primary-hover)] disabled:opacity-50 disabled:cursor-not-allowed
                       max-sm:w-full max-sm:justify-center"
          >
            {saving && <Spinner size={13} />}
            {saving ? t('modal.edit.savingBtn') : t('modal.edit.saveBtn')}
          </button>
        </div>
      </div>
    </div>
  )
}
