/**
 * AddWorldModal — S6 Modal añadir mundo.
 *
 * Spec: docs/design/gestion-cuentas-mundos.md §6 S6, §7 S6, §9 S6
 * Mockup: cuenta-detalle.playground.html (vista "Añadir mundo")
 *
 * - URL del servidor + Tribu (select).
 * - Vista previa parseada ("ts1 · x1 · international") en tiempo real (200ms debounce).
 * - POST /accounts/:id/worlds → { server, tribe } → 201.
 * - 409 → error inline bajo URL (server duplicado).
 * - 422 → error inline bajo URL (URL inválida).
 * - CERO texto hardcodeado.
 */
import { useState, useEffect, useRef, useMemo } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api, ApiError } from '../../api/client.js'
import { parseServerUrl, isValidServerUrl, Spinner, useFocusTrap, showToast } from './uiUtils.jsx'

// ─── Tribus ───────────────────────────────────────────────────────────────────
const TRIBES = ['romans', 'teutons', 'gauls', 'egyptians', 'huns', 'spartans', 'vikings']

// ─── Estilos base ─────────────────────────────────────────────────────────────
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

// ─── AddWorldModal ────────────────────────────────────────────────────────────

/**
 * @param {object} props
 * @param {string|number} props.accountId
 * @param {Function} props.onClose
 * @param {Function} props.onAdded — (newWorld) => void
 * @param {React.RefObject} props.triggerRef
 */
export function AddWorldModal({ accountId, onClose, onAdded, triggerRef }) {
  const { t } = useI18n()
  const modalRef  = useRef(null)
  const serverRef = useRef(null)

  const [serverUrl, setServerUrl] = useState('')
  const [tribe,     setTribe]     = useState('')
  const [serverErr, setServerErr] = useState('')
  const [adding,    setAdding]    = useState(false)

  // Vista previa debounced
  const [preview, setPreview] = useState(null)
  useEffect(() => {
    const timer = setTimeout(() => {
      setPreview(parseServerUrl(serverUrl))
    }, 200)
    return () => clearTimeout(timer)
  }, [serverUrl])

  useFocusTrap(modalRef, true)

  // Foco al primer campo al abrir
  useEffect(() => {
    const timer = setTimeout(() => serverRef.current?.focus(), 50)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    function handler(e) {
      if (e.key === 'Escape' && !adding) handleClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [adding]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleClose() {
    onClose()
    triggerRef?.current?.focus()
  }

  function handleBackdropClick(e) {
    if (!adding && e.target === e.currentTarget) handleClose()
  }

  const canAdd = useMemo(
    () => serverUrl.trim() && isValidServerUrl(serverUrl.trim()) && tribe && !adding,
    [serverUrl, tribe, adding]
  )

  async function handleAdd() {
    if (!canAdd) {
      if (!serverUrl.trim() || !isValidServerUrl(serverUrl.trim()))
        setServerErr(t('wizard.error.server.invalid'))
      return
    }
    setServerErr('')
    setAdding(true)
    try {
      const world = await api.createWorld(accountId, {
        server: serverUrl.trim(),
        tribe,
      })
      showToast(t('modal.addWorld.toast'))
      onAdded(world)
      handleClose()
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) setServerErr(t('wizard.error.server.taken'))
        else if (err.status === 422) setServerErr(t('wizard.error.server.invalid'))
        else showToast(t('error.network'))
      } else {
        showToast(t('error.network'))
      }
    } finally {
      setAdding(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[400] flex items-center justify-center
                 bg-black/40 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="addWorldModalTitle"
      onClick={handleBackdropClick}
    >
      <div
        ref={modalRef}
        className="bg-[var(--surface)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)]
                   flex flex-col max-h-[90vh]
                   w-[min(440px,92vw)]
                   max-sm:w-full max-sm:rounded-b-none max-sm:self-end"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-3 px-5 pt-[18px] pb-[14px]
                        border-b border-[var(--border)] flex-shrink-0">
          <span id="addWorldModalTitle"
            className="text-[17px] font-semibold tracking-[-0.01em] text-[var(--text)]">
            {t('modal.addWorld.title')}
          </span>
          <button
            type="button"
            onClick={handleClose}
            aria-label="Cerrar"
            className="w-7 h-7 rounded-[var(--radius-sm)] grid place-items-center
                       text-[var(--text-secondary)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]
                       text-[18px] leading-none flex-shrink-0 border-0 bg-transparent cursor-pointer"
          >
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="p-5 overflow-y-auto flex-1">
          {/* URL del servidor */}
          <FormField label={t('wizard.field.server')} required error={serverErr}>
            <input
              ref={serverRef}
              type="url"
              value={serverUrl}
              onChange={e => { setServerUrl(e.target.value); setServerErr('') }}
              onBlur={() => {
                if (!serverUrl.trim()) setServerErr(t('wizard.error.required'))
                else if (!isValidServerUrl(serverUrl.trim())) setServerErr(t('wizard.error.server.invalid'))
              }}
              placeholder={t('wizard.field.server.ph')}
              disabled={adding}
              className={`${inputBase} ${serverErr ? inputError : ''}`}
              aria-invalid={!!serverErr}
            />
            {/* Vista previa parseada */}
            <div
              className="text-[12px] mt-[3px]"
              aria-live="polite"
            >
              {serverUrl ? (
                preview
                  ? <span className="text-[var(--accent-text)] font-mono">{preview}</span>
                  : <span className="text-[var(--text-tertiary)]">—</span>
              ) : null}
            </div>
          </FormField>

          {/* Tribu */}
          <FormField label={t('wizard.field.tribe')} required>
            <select
              value={tribe}
              onChange={e => setTribe(e.target.value)}
              disabled={adding}
              className={`${inputBase} cursor-pointer`}
            >
              <option value="">{t('wizard.field.tribe.ph')}</option>
              {TRIBES.map(tr => (
                <option key={tr} value={tr}>{t(`tribe.${tr}`)}</option>
              ))}
            </select>
          </FormField>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-[14px]
                        border-t border-[var(--border)] flex-shrink-0
                        max-sm:flex-col-reverse max-sm:items-stretch">
          <button
            type="button"
            onClick={handleClose}
            disabled={adding}
            className="h-8 px-[14px] rounded-[var(--radius-sm)] border border-[var(--border-strong)]
                       bg-[var(--surface)] text-[var(--text)] text-[13px] font-[inherit]
                       cursor-pointer inline-flex items-center gap-[6px] whitespace-nowrap
                       hover:bg-[var(--surface-2)] disabled:opacity-50 disabled:cursor-not-allowed
                       max-sm:w-full max-sm:justify-center"
          >
            {t('modal.addWorld.cancelBtn')}
          </button>
          <button
            type="button"
            onClick={handleAdd}
            disabled={!canAdd}
            className="h-8 px-[14px] rounded-[var(--radius-sm)] border-0
                       bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)]
                       text-[13px] font-medium font-[inherit] cursor-pointer
                       inline-flex items-center gap-[6px] whitespace-nowrap
                       hover:bg-[var(--btn-primary-hover)] disabled:opacity-50 disabled:cursor-not-allowed
                       max-sm:w-full max-sm:justify-center"
          >
            {adding && <Spinner size={13} />}
            {adding ? t('modal.addWorld.addingBtn') : t('modal.addWorld.addBtn')}
          </button>
        </div>
      </div>
    </div>
  )
}
