/**
 * ConfirmDeleteModal — S7 (borrar cuenta) y S8 (borrar mundo).
 *
 * Spec: docs/design/gestion-cuentas-mundos.md §6 S7/S8, §7 S7/S8, §9 S7/S8
 * Mockup: cuenta-detalle.playground.html (vistas "Borrar cuenta" y "Borrar mundo")
 *
 * Patrón visual:
 * - Estado normal: texto de confirmación + "Cancelar" + "Borrar" (rojo relleno).
 * - Estado 409: error-block inline (⚠ fondo danger 8% + borde start 3px danger),
 *   botón "Borrar" se reemplaza por "Cerrar".
 * - "Borrar" deshabilitado + spinner durante la operación.
 * - Focus trap, ESC, backdrop click para cerrar (solo si no hay operación en curso).
 * - CERO texto hardcodeado.
 */
import { useState, useEffect, useRef } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { ApiError } from '../../api/client.js'
import { Spinner, useFocusTrap, showToast } from './uiUtils.jsx'

// ─── Icono warning ────────────────────────────────────────────────────────────
function IconWarning({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
      style={{ flexShrink: 0, marginTop: '1px' }}>
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

// ─── ConfirmDeleteModal ───────────────────────────────────────────────────────

/**
 * @param {object} props
 * @param {'account'|'world'} props.type — 'account' = S7, 'world' = S8
 * @param {string} props.title    — título del modal (ya traducido)
 * @param {string} props.question — pregunta de confirmación (ya traducida, con nombre)
 * @param {string} props.warning  — texto de advertencia (ya traducido)
 * @param {Function} props.onConfirm — async () => void — debe lanzar ApiError si 409
 * @param {Function} props.onClose
 * @param {React.RefObject} props.triggerRef
 */
export function ConfirmDeleteModal({ title, question, warning, onConfirm, onClose, triggerRef }) {
  const { t } = useI18n()
  const modalRef = useRef(null)

  const [deleting, setDeleting] = useState(false)
  // null = normal | 'active' = 409 sesión activa | 'error' = red error
  const [errorState, setErrorState] = useState(null)
  const [errorMsg,   setErrorMsg]   = useState('')

  useFocusTrap(modalRef, true)

  // Foco al botón de cancelar (o cerrar) al abrir
  useEffect(() => {
    const timer = setTimeout(() => {
      // Foco al primer botón focusable (cancelar)
      modalRef.current?.querySelector('button')?.focus()
    }, 50)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    function handler(e) {
      if (e.key === 'Escape' && !deleting) handleClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [deleting]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleClose() {
    onClose()
    triggerRef?.current?.focus()
  }

  function handleBackdropClick(e) {
    if (!deleting && e.target === e.currentTarget) handleClose()
  }

  async function handleConfirm() {
    setDeleting(true)
    setErrorState(null)
    try {
      await onConfirm()
      // onConfirm cierra el modal y actualiza la lista desde el padre
      handleClose()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Error de sesión activa — mostrar inline en el modal
        setErrorState('active')
        setErrorMsg(
          title.toLowerCase().includes('cuenta') || title.toLowerCase().includes('account')
            ? t('modal.deleteAccount.active')
            : t('modal.deleteWorld.active')
        )
      } else {
        showToast(t('error.network'))
      }
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[400] flex items-center justify-center
                 bg-black/40 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirmDeleteTitle"
      onClick={handleBackdropClick}
    >
      <div
        ref={modalRef}
        className="bg-[var(--surface)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)]
                   flex flex-col max-h-[90vh]
                   w-[min(420px,92vw)]
                   max-sm:w-full max-sm:rounded-b-none max-sm:self-end"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-3 px-5 pt-[18px] pb-[14px]
                        border-b border-[var(--border)] flex-shrink-0">
          <span id="confirmDeleteTitle"
            className="text-[17px] font-semibold tracking-[-0.01em] text-[var(--text)]">
            {title}
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
          {errorState === 'active' ? (
            /* Error 409 — error-block inline (spec §6 S7/S8) */
            <div
              role="alert"
              className="flex gap-[10px] p-[12px_14px] rounded-[var(--radius-sm)] mb-1"
              style={{
                background: 'rgba(201,53,44,.08)',
                borderInlineStart: '3px solid var(--danger)',
              }}
            >
              <span className="text-[var(--danger)]"><IconWarning /></span>
              <span className="text-[13px] text-[var(--text)] leading-[1.4] flex-1">
                {errorMsg}
              </span>
            </div>
          ) : (
            <>
              <p className="text-[15px] font-semibold mb-2 leading-[1.3] text-[var(--text)]">
                {question}
              </p>
              <p className="text-[13px] text-[var(--text-secondary)] leading-[1.5]">
                {warning}
              </p>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-[14px]
                        border-t border-[var(--border)] flex-shrink-0
                        max-sm:flex-col-reverse max-sm:items-stretch">
          {errorState === 'active' ? (
            /* Solo "Cerrar" cuando hay 409 */
            <button
              type="button"
              onClick={handleClose}
              className="h-8 px-[14px] rounded-[var(--radius-sm)] border border-[var(--border-strong)]
                         bg-[var(--surface)] text-[var(--text)] text-[13px] font-[inherit]
                         cursor-pointer inline-flex items-center gap-[6px] whitespace-nowrap
                         hover:bg-[var(--surface-2)]
                         max-sm:w-full max-sm:justify-center"
            >
              {t('modal.deleteAccount.close')}
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={handleClose}
                disabled={deleting}
                className="h-8 px-[14px] rounded-[var(--radius-sm)] border border-[var(--border-strong)]
                           bg-[var(--surface)] text-[var(--text)] text-[13px] font-[inherit]
                           cursor-pointer inline-flex items-center gap-[6px] whitespace-nowrap
                           hover:bg-[var(--surface-2)] disabled:opacity-50 disabled:cursor-not-allowed
                           max-sm:w-full max-sm:justify-center"
              >
                {t('modal.deleteAccount.cancel')}
              </button>
              {/* Botón "Borrar" — rojo relleno (btn-danger del mockup) */}
              <button
                type="button"
                onClick={handleConfirm}
                disabled={deleting}
                className="h-8 px-[14px] rounded-[var(--radius-sm)] border-0
                           bg-[var(--danger)] text-white
                           text-[13px] font-medium font-[inherit] cursor-pointer
                           inline-flex items-center gap-[6px] whitespace-nowrap
                           hover:opacity-[.88] disabled:opacity-50 disabled:cursor-not-allowed
                           max-sm:w-full max-sm:justify-center"
              >
                {deleting && <Spinner size={13} />}
                {t('modal.deleteAccount.confirm')}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
