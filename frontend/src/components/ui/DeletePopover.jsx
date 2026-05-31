/**
 * DeletePopover — Confirmación inline ligera anclada a un elemento.
 *
 * Menos intrusivo que un modal de pantalla completa. Se renderiza como
 * un popover pequeño con fondo de surface, sombra y foco trampa básico.
 *
 * Accesibilidad:
 *  - role="dialog" + aria-modal + aria-labelledby
 *  - Al montarse, foco va al botón de Borrar
 *  - Escape cierra y devuelve foco al trigger
 *  - Tab cicla entre Borrar / Cancelar
 *
 * Props:
 *   question   — string (pregunta ya traducida)
 *   confirmLabel — string ("Borrar")
 *   cancelLabel  — string ("Cancelar")
 *   onConfirm  — () => void
 *   onCancel   — () => void
 *   loading    — boolean (mientras se procesa el borrado)
 *   triggerRef — React.RefObject para devolver el foco al cerrar
 */
import { useEffect, useRef } from 'react'
import { Spinner } from './uiUtils.jsx'

export function DeletePopover({ question, confirmLabel, cancelLabel, onConfirm, onCancel, loading, triggerRef }) {
  const popoverRef = useRef(null)
  const confirmBtnRef = useRef(null)

  // Foco al botón de Borrar al montar
  useEffect(() => {
    const timer = setTimeout(() => confirmBtnRef.current?.focus(), 30)
    return () => clearTimeout(timer)
  }, [])

  // Escape cierra
  useEffect(() => {
    function handler(e) {
      if (e.key === 'Escape' && !loading) {
        onCancel()
        triggerRef?.current?.focus()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [loading, onCancel, triggerRef])

  // Focus trap entre los dos botones
  useEffect(() => {
    function handler(e) {
      if (e.key !== 'Tab' || !popoverRef.current) return
      const focusable = Array.from(
        popoverRef.current.querySelectorAll('button:not([disabled])')
      )
      if (!focusable.length) return
      const first = focusable[0]
      const last  = focusable[focusable.length - 1]
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus() }
      } else {
        if (document.activeElement === last)  { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  return (
    <div
      ref={popoverRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-popover-question"
      style={{
        position: 'absolute',
        zIndex: 200,
        insetInlineEnd: 0,
        top: '100%',
        marginTop: '4px',
        background: 'var(--surface)',
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-lg)',
        padding: '12px 14px',
        minWidth: '220px',
        maxWidth: '280px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
      onClick={(e) => e.stopPropagation()}
    >
      <p
        id="delete-popover-question"
        style={{
          margin: 0,
          fontSize: '13px',
          color: 'var(--text)',
          lineHeight: 1.4,
        }}
      >
        {question}
      </p>
      <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
        <button
          type="button"
          onClick={() => { onCancel(); triggerRef?.current?.focus() }}
          disabled={loading}
          style={{
            height: '28px',
            padding: '0 12px',
            background: 'var(--surface)',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '12px',
            color: 'var(--text)',
            cursor: 'pointer',
            fontFamily: 'inherit',
            opacity: loading ? 0.5 : 1,
          }}
        >
          {cancelLabel}
        </button>
        <button
          ref={confirmBtnRef}
          type="button"
          onClick={onConfirm}
          disabled={loading}
          style={{
            height: '28px',
            padding: '0 12px',
            background: 'var(--danger)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            fontSize: '12px',
            color: '#fff',
            cursor: loading ? 'not-allowed' : 'pointer',
            fontFamily: 'inherit',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '5px',
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading && <Spinner size={11} />}
          {confirmLabel}
        </button>
      </div>
    </div>
  )
}
