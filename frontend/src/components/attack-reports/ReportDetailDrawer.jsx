/**
 * ReportDetailDrawer — Drawer lateral con el detalle completo de un reporte.
 *
 * Patrón §19.11 de DESIGN.md: position:fixed, desliza desde end,
 * 480px desktop / 100vw móvil. Backdrop semitransparente.
 *
 * Accesibilidad:
 *  - role="dialog" aria-modal aria-labelledby
 *  - Foco al botón [×] al abrir; vuelve a la fila al cerrar
 *  - Scroll de página bloqueado mientras el drawer está abierto
 *  - Escape cierra
 *  - Reducción de movimiento respetada
 *
 * Props:
 *   reportId   — number | null (null = cerrado)
 *   onClose    — () => void
 *   onDelete   — (id) => Promise<void>
 *   returnRef  — React.RefObject (elemento al que volver el foco al cerrar)
 *   lang       — string
 */
import { useState, useEffect, useRef } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api } from '../../api/client.js'
import { useFocusTrap, Spinner } from '../ui/uiUtils.jsx'
import { DeletePopover } from '../ui/DeletePopover.jsx'
import { ReportPreview } from './ReportPreview.jsx'
import { ResIcon } from '../combat/TravianReport.jsx'
import { formatDateVerbatim } from '../../utils/formatDateVerbatim.js'

// attacked_at: hora verbatim del servidor Travian — no pasar por new Date()
function formatDate(isoStr) {
  return formatDateVerbatim(isoStr)
}

// created_at: hora local del sistema del usuario — SÍ usa Intl con zona horaria
function formatCreatedAt(isoStr, lang) {
  if (!isoStr) return '—'
  try {
    return new Intl.DateTimeFormat(lang, {
      day: '2-digit', month: '2-digit', year: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    }).format(new Date(isoStr))
  } catch {
    return isoStr
  }
}

function formatCoord(n) {
  if (n == null) return '—'
  return n < 0 ? `−${Math.abs(n)}` : `${n}`
}

function HeroInventory({ inv, t }) {
  if (!inv) {
    return (
      <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-tertiary)', fontStyle: 'italic' }}>
        {t('ar.drawer.hero.none')}
      </p>
    )
  }
  const items = [
    { res: 'wood', value: inv.wood },
    { res: 'clay', value: inv.clay },
    { res: 'iron', value: inv.iron },
    { res: 'crop', value: inv.crop },
  ].filter((i) => i.value != null && i.value > 0)
  if (!items.length) return (
    <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-tertiary)', fontStyle: 'italic' }}>
      {t('ar.drawer.hero.none')}
    </p>
  )
  return (
    <p style={{ margin: 0, fontSize: '13px', color: 'var(--text)', display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
      <span style={{ color: 'var(--text-secondary)', marginInlineEnd: '4px' }}>{t('ar.drawer.hero.title')}</span>
      {items.map(({ res, value }) => (
        <span key={res} style={{ display: 'flex', alignItems: 'center', gap: '3px', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
          {value.toLocaleString()} <ResIcon res={res} size={14} />
        </span>
      ))}
    </p>
  )
}

export function ReportDetailDrawer({ reportId, onClose, onDelete, returnRef, lang }) {
  const { t } = useI18n()
  const drawerRef  = useRef(null)
  const closeBtnRef = useRef(null)
  const deleteBtnRef = useRef(null)

  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)
  const [showDeletePopover, setShowDeletePopover] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const isOpen = reportId != null

  useFocusTrap(drawerRef, isOpen)

  // Cargar datos al abrir
  useEffect(() => {
    if (!isOpen) { setData(null); return }
    setLoading(true)
    setError(null)
    setData(null)
    api.getAttackReport(reportId)
      .then((d) => { setData(d); setLoading(false) })
      .catch((err) => { setError(err?.detail ?? t('ar.drawer.error')); setLoading(false) })
  }, [reportId, t])

  // Foco al botón [×] al abrir
  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => closeBtnRef.current?.focus(), 60)
      return () => clearTimeout(timer)
    }
  }, [isOpen])

  // Bloquear scroll al abrir
  useEffect(() => {
    if (isOpen) {
      const prev = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      return () => { document.body.style.overflow = prev }
    }
  }, [isOpen])

  // Escape cierra
  useEffect(() => {
    function handler(e) {
      if (e.key === 'Escape' && isOpen && !deleting) {
        handleClose()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [isOpen, deleting])

  function handleClose() {
    onClose()
    setTimeout(() => returnRef?.current?.focus(), 60)
  }

  async function handleDelete() {
    if (!data) return
    setDeleting(true)
    try {
      await onDelete(data.id)
      setShowDeletePopover(false)
      handleClose()
    } catch (err) {
      setError(err?.detail ?? t('ar.drawer.error'))
      setDeleting(false)
    }
  }

  if (!isOpen) return null

  const titleId = 'drawer-report-title'

  return (
    <>
      {/* Backdrop — centra el modal */}
      <div
        aria-hidden="true"
        onClick={handleClose}
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 299,
          background: 'rgba(0,0,0,0.45)',
          backdropFilter: 'blur(2px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          animation: 'backdrop-in 150ms ease both',
        }}
      >
        {/* Modal central */}
        <div
          ref={drawerRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={(e) => e.stopPropagation()}
          style={{
            width: 'min(920px, 96vw)',
            maxHeight: '90vh',
            zIndex: 300,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-lg)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            animation: 'modal-pop 200ms ease both',
          }}
        >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '14px 16px',
            borderBottom: '1px solid var(--border)',
            position: 'sticky',
            top: 0,
            background: 'var(--surface)',
            zIndex: 1,
          }}
        >
          <h2
            id={titleId}
            style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text)' }}
          >
            {t('ar.drawer.title').replace('{id}', reportId)}
          </h2>
          <button
            ref={closeBtnRef}
            type="button"
            aria-label={t('ar.drawer.close')}
            onClick={handleClose}
            style={{
              width: '28px',
              height: '28px',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'transparent',
              border: '1px solid transparent',
              borderRadius: 'var(--radius-sm)',
              fontSize: '14px',
              cursor: 'pointer',
              color: 'var(--text-secondary)',
              fontFamily: 'inherit',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.background = 'var(--surface-2)' }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'transparent'; e.currentTarget.style.background = 'transparent' }}
          >
            ×
          </button>
        </div>

        {/* Cuerpo (scrollea dentro del modal) */}
        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Estado cargando */}
          {loading && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {/* Skeleton */}
              <div style={{ height: '14px', background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)', width: '60%', animation: 'pulse 1.4s ease-in-out infinite' }} />
              <div style={{ height: '12px', background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)', width: '40%', animation: 'pulse 1.4s ease-in-out infinite' }} />
              <div style={{ height: '160px', background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)', animation: 'pulse 1.4s ease-in-out infinite' }} />
              <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-tertiary)' }}>{t('ar.drawer.loading')}</p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div role="alert" style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px', background: 'var(--danger-subtle, color-mix(in srgb, var(--danger) 10%, transparent))', border: '1px solid var(--danger)', borderRadius: 'var(--radius-sm)' }}>
              <p style={{ margin: 0, fontSize: '13px', color: 'var(--text)' }}>{error}</p>
              <button
                type="button"
                onClick={() => {
                  setError(null)
                  setLoading(true)
                  api.getAttackReport(reportId)
                    .then((d) => { setData(d); setLoading(false) })
                    .catch((err) => { setError(err?.detail ?? t('ar.drawer.error')); setLoading(false) })
                }}
                style={{
                  alignSelf: 'flex-start',
                  background: 'var(--btn-primary-bg)',
                  color: 'var(--btn-primary-text)',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  padding: '4px 10px',
                  fontSize: '12px',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >
                {t('ar.drawer.retry')}
              </button>
            </div>
          )}

          {/* Datos */}
          {data && !loading && (
            <>
              {/* Sub-info: coords · fecha · aldea */}
              <div style={{ fontSize: '13px', color: 'var(--text-secondary)', display: 'flex', flexWrap: 'wrap', gap: '4px 10px' }}>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)', fontWeight: 600 }}>
                  {`(${formatCoord(data.coord_x_dest)}|${formatCoord(data.coord_y_dest)})`}
                </span>
                <span aria-hidden="true" style={{ color: 'var(--border-strong)' }}>·</span>
                <span>{formatDate(data.attacked_at)}</span>
                {data.origin_village_name && (
                  <>
                    <span aria-hidden="true" style={{ color: 'var(--border-strong)' }}>·</span>
                    <span style={{ fontStyle: 'italic' }}>&ldquo;{data.origin_village_name}&rdquo;</span>
                  </>
                )}
              </div>

              {/* Fecha de guardado */}
              {data.created_at && (
                <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-tertiary)' }}>
                  {t('ar.drawer.savedAt').replace('{date}', formatCreatedAt(data.created_at, lang))}
                </p>
              )}

              <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: 0 }} />

              {/* TravianReport */}
              <ReportPreview
                data={data}
                lang={lang}
                onViewExisting={() => {}}
                t={t}
              />

              <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: 0 }} />

              {/* Inventario del héroe */}
              <HeroInventory inv={data.hero_inventory} t={t} />
            </>
          )}
        </div>

        {/* Footer con botón borrar */}
        {data && !loading && (
          <div
            style={{
              padding: '12px 16px',
              borderTop: '1px solid var(--border)',
              display: 'flex',
              justifyContent: 'flex-end',
              position: 'sticky',
              bottom: 0,
              background: 'var(--surface)',
              zIndex: 1,
            }}
          >
            <div style={{ position: 'relative' }}>
              <button
                ref={deleteBtnRef}
                type="button"
                onClick={() => setShowDeletePopover((v) => !v)}
                style={{
                  height: '34px',
                  padding: '0 14px',
                  background: 'transparent',
                  color: 'var(--danger)',
                  border: '1px solid var(--danger)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                  fontFamily: 'inherit',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                {deleting && <Spinner size={12} />}
                {t('ar.drawer.delete')}
              </button>
              {showDeletePopover && (
                <div style={{ position: 'absolute', bottom: '100%', insetInlineEnd: 0, marginBottom: '4px' }}>
                  <DeletePopover
                    question={t('ar.delete.question')}
                    confirmLabel={t('ar.delete.confirm')}
                    cancelLabel={t('ar.delete.cancel')}
                    onConfirm={handleDelete}
                    onCancel={() => setShowDeletePopover(false)}
                    loading={deleting}
                    triggerRef={deleteBtnRef}
                  />
                </div>
              )}
            </div>
          </div>
        )}
        </div>
      </div>

      <style>{`
        @keyframes backdrop-in {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes modal-pop {
          from { opacity: 0; transform: scale(0.96); }
          to   { opacity: 1; transform: scale(1); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.5; }
        }
        @media (prefers-reduced-motion: reduce) {
          [style*="modal-pop"],
          [style*="backdrop-in"] { animation: none !important; }
        }
      `}</style>
    </>
  )
}
