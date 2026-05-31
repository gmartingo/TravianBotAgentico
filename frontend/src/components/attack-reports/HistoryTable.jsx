/**
 * HistoryTable — Tabla densa del historial de reportes de oasis.
 *
 * Desktop/tablet (md+): tabla completa con columnas P1+P2.
 * Móvil (<md): tarjetas apiladas con columnas P1 únicamente.
 *
 * Gestiona el popover de borrado inline (DeletePopover) anclado a cada fila.
 * La fila desaparece con opacity → 0 en 220ms tras confirmar el borrado.
 *
 * Props:
 *   items         — array de reportes del backend
 *   total         — número total de reportes (para paginación y caption)
 *   page          — página actual (1-based)
 *   pageSize      — tamaño de página
 *   onPageChange  — (page) => void
 *   onRowClick    — (id) => void — abre el drawer de detalle
 *   onDelete      — (id) => Promise<void>
 *   cumulativeBounty — number | null (botín acumulado del rango)
 *   lang          — string (idioma activo)
 */
import { useState, useRef, useCallback } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { DeletePopover } from '../ui/DeletePopover.jsx'
import { Spinner } from '../ui/uiUtils.jsx'
import { formatDateVerbatim } from '../../utils/formatDateVerbatim.js'

// ── Helpers ─────────────────────────────────────────────────────────────────

function formatCoord(n) {
  if (n == null) return '—'
  return n < 0 ? `−${Math.abs(n)}` : `${n}`
}

function formatCoords(x, y) {
  return `(${formatCoord(x)}|${formatCoord(y)})`
}

// attacked_at es verbatim (hora del servidor Travian) — no pasar por new Date()
function formatDate(isoStr) {
  return formatDateVerbatim(isoStr)
}

function formatBounty(n, lang) {
  if (n == null) return '—'
  return new Intl.NumberFormat(lang).format(Math.round(n))
}

// ── Skeleton de filas ────────────────────────────────────────────────────────
function SkeletonRow() {
  return (
    <tr aria-hidden="true">
      {[1, 2, 3, 4, 5].map((i) => (
        <td key={i} style={{ padding: '10px 12px' }}>
          <div style={{
            height: '12px',
            background: 'var(--surface-2)',
            borderRadius: 'var(--radius-sm)',
            width: i === 1 ? '80px' : i === 2 ? '70px' : i === 3 ? '90px' : i === 4 ? '50px' : '40px',
            animation: 'pulse 1.4s ease-in-out infinite',
          }} />
        </td>
      ))}
    </tr>
  )
}

// ── Fila de la tabla ─────────────────────────────────────────────────────────
function ReportRow({ item, onRowClick, onDelete, lang, t }) {
  const [showPopover, setShowPopover] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [disappearing, setDisappearing] = useState(false)
  const deleteRef = useRef(null)

  const coordStr = formatCoords(item.coord_x_dest, item.coord_y_dest)
  const dateStr  = formatDate(item.attacked_at)
  const bountyTotal = item.cumulative_bounty != null
    ? null  // la suma acumulada es del rango, no de cada fila
    : null

  // Calcular botín de la fila desde animals_summary si está disponible,
  // o desde los campos directos del reporte
  const rowBounty = item.bounty_total ?? (
    item.bounty
      ? (item.bounty.wood ?? 0) + (item.bounty.clay ?? 0) + (item.bounty.iron ?? 0) + (item.bounty.crop ?? 0)
      : null
  )

  // Bajas del atacante (suma de lost de cada tropa)
  const attackerLosses = item.attacker_losses_count ??
    (item.attacker_troops?.reduce((s, t) => s + (t.lost ?? 0), 0) ?? null)

  async function handleConfirmDelete() {
    setDeleting(true)
    try {
      await onDelete(item.id)
      setShowPopover(false)
      // Animación de desaparición (220ms)
      setDisappearing(true)
    } catch {
      setDeleting(false)
    }
  }

  // El row se oculta visualmente tras borrar (onDelete elimina del DOM vía re-fetch)
  const rowStyle = {
    transition: 'opacity 220ms ease',
    opacity: disappearing ? 0 : 1,
    cursor: 'pointer',
  }

  return (
    <tr
      role="row"
      style={rowStyle}
      onClick={(e) => {
        // No abrir drawer si el clic fue en la zona de acciones
        if (e.target.closest('[data-actions]')) return
        onRowClick(item.id)
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-2)' }}
      onMouseLeave={(e) => { e.currentTarget.style.background = '' }}
    >
      {/* Fecha */}
      <td style={{ padding: '8px 12px', fontSize: '13px', color: 'var(--text)', whiteSpace: 'nowrap' }}>
        {dateStr}
      </td>
      {/* Oasis coords */}
      <td style={{ padding: '8px 12px', fontSize: '13px', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
        {coordStr}
      </td>
      {/* Desde (aldea origen, P2 — oculto en móvil) */}
      <td className="hidden md:table-cell" style={{ padding: '8px 12px', fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {item.origin_village_name ?? '—'}
      </td>
      {/* Botín total */}
      <td style={{ padding: '8px 12px', fontSize: '13px', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', textAlign: 'end' }}>
        {rowBounty != null ? formatBounty(rowBounty, lang) : '—'}
      </td>
      {/* Bajas atacante (P2 — oculto en móvil) */}
      <td className="hidden md:table-cell" style={{ padding: '8px 12px', fontSize: '13px', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', textAlign: 'end', color: attackerLosses ? 'var(--danger)' : 'var(--text-secondary)' }}>
        {attackerLosses != null ? attackerLosses : '—'}
      </td>
      {/* Acciones */}
      <td data-actions="true" style={{ padding: '8px 8px', whiteSpace: 'nowrap', position: 'relative' }}>
        <div style={{ display: 'flex', gap: '4px', justifyContent: 'flex-end', alignItems: 'center' }}>
          {/* Borrar */}
          <div style={{ position: 'relative' }}>
            <button
              ref={deleteRef}
              type="button"
              aria-label={t('ar.history.delete.aria')}
              onClick={(e) => { e.stopPropagation(); setShowPopover((v) => !v) }}
              style={{
                width: '28px',
                height: '28px',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'transparent',
                border: '1px solid transparent',
                borderRadius: 'var(--radius-sm)',
                cursor: 'pointer',
                color: 'var(--text-tertiary)',
                fontSize: '13px',
                transition: 'color var(--dur-fast), border-color var(--dur-fast)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = 'var(--danger)'
                e.currentTarget.style.borderColor = 'var(--danger)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = 'var(--text-tertiary)'
                e.currentTarget.style.borderColor = 'transparent'
              }}
            >
              {deleting ? <Spinner size={11} /> : '🗑'}
            </button>
            {showPopover && (
              <DeletePopover
                question={t('ar.delete.question')}
                confirmLabel={t('ar.delete.confirm')}
                cancelLabel={t('ar.delete.cancel')}
                onConfirm={handleConfirmDelete}
                onCancel={() => setShowPopover(false)}
                loading={deleting}
                triggerRef={deleteRef}
              />
            )}
          </div>
          {/* Ver detalle */}
          <button
            type="button"
            aria-label={t('ar.history.detail.aria')}
            onClick={(e) => { e.stopPropagation(); onRowClick(item.id) }}
            style={{
              width: '28px',
              height: '28px',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'transparent',
              border: '1px solid transparent',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              color: 'var(--text-tertiary)',
              fontSize: '12px',
              transition: 'color var(--dur-fast), border-color var(--dur-fast)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = 'var(--text)'
              e.currentTarget.style.borderColor = 'var(--border)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = 'var(--text-tertiary)'
              e.currentTarget.style.borderColor = 'transparent'
            }}
          >
            ▶
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── Tarjeta móvil ────────────────────────────────────────────────────────────
function ReportCard({ item, onRowClick, onDelete, lang, t }) {
  const [showPopover, setShowPopover] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [disappearing, setDisappearing] = useState(false)
  const deleteRef = useRef(null)

  const coordStr = formatCoords(item.coord_x_dest, item.coord_y_dest)
  const dateStr  = formatDate(item.attacked_at)
  const rowBounty = item.bounty_total ?? (
    item.bounty
      ? (item.bounty.wood ?? 0) + (item.bounty.clay ?? 0) + (item.bounty.iron ?? 0) + (item.bounty.crop ?? 0)
      : null
  )

  async function handleConfirmDelete() {
    setDeleting(true)
    try {
      await onDelete(item.id)
      setShowPopover(false)
      setDisappearing(true)
    } catch {
      setDeleting(false)
    }
  }

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        padding: '10px 12px',
        background: 'var(--surface)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '8px',
        opacity: disappearing ? 0 : 1,
        transition: 'opacity 220ms ease',
        cursor: 'pointer',
      }}
      onClick={() => onRowClick(item.id)}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '2px' }}>{dateStr}</div>
        <div style={{ fontSize: '14px', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', color: 'var(--text)', fontWeight: 600 }}>{coordStr}</div>
        {rowBounty != null && (
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', marginTop: '2px' }}>
            {formatBounty(rowBounty, lang)}
          </div>
        )}
      </div>
      <div data-actions="true" style={{ position: 'relative', display: 'flex', gap: '4px' }}>
        <div style={{ position: 'relative' }}>
          <button
            ref={deleteRef}
            type="button"
            aria-label={t('ar.history.delete.aria')}
            onClick={(e) => { e.stopPropagation(); setShowPopover((v) => !v) }}
            style={{ width: '32px', height: '32px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'transparent', border: 'none', cursor: 'pointer', fontSize: '15px' }}
          >
            {deleting ? <Spinner size={12} /> : '🗑'}
          </button>
          {showPopover && (
            <DeletePopover
              question={t('ar.delete.question')}
              confirmLabel={t('ar.delete.confirm')}
              cancelLabel={t('ar.delete.cancel')}
              onConfirm={handleConfirmDelete}
              onCancel={() => setShowPopover(false)}
              loading={deleting}
              triggerRef={deleteRef}
            />
          )}
        </div>
        <button
          type="button"
          aria-label={t('ar.history.detail.aria')}
          onClick={(e) => { e.stopPropagation(); onRowClick(item.id) }}
          style={{ width: '32px', height: '32px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '13px' }}
        >
          ▶
        </button>
      </div>
    </div>
  )
}

// ── Componente principal ─────────────────────────────────────────────────────
export function HistoryTable({ items, total, page, pageSize, onPageChange, onRowClick, onDelete, cumulativeBounty, lang, loading }) {
  const { t } = useI18n()
  const totalPages = Math.ceil(total / pageSize) || 1
  const from = (page - 1) * pageSize + 1
  const to   = Math.min(page * pageSize, total)

  const countKey = total === 1 ? 'ar.history.count' : 'ar.history.count.pl'
  const countStr = t(countKey).replace('{n}', new Intl.NumberFormat('es').format(total))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {/* Caption de total */}
      <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
        {countStr}
      </div>

      {/* ── Tabla (md+) ───────────────────────────────────────────── */}
      <div className="hidden md:block" style={{ overflowX: 'auto' }}>
        <table
          role="table"
          style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}
        >
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {[
                { key: 'date',   label: t('ar.history.col.date'),    cls: '' },
                { key: 'oasis',  label: t('ar.history.col.oasis'),   cls: '' },
                { key: 'from',   label: t('ar.history.col.from'),    cls: 'hidden md:table-cell' },
                { key: 'bounty', label: t('ar.history.col.bounty'),  cls: '', align: 'end' },
                { key: 'losses', label: t('ar.history.col.losses'),  cls: 'hidden md:table-cell', align: 'end' },
                { key: 'actions',label: t('ar.history.col.actions'), cls: '', align: 'end' },
              ].map(({ key, label, cls, align }) => (
                <th
                  key={key}
                  scope="col"
                  className={cls}
                  style={{
                    padding: '6px 12px',
                    textAlign: align ?? 'start',
                    fontSize: '11px',
                    color: 'var(--text-tertiary)',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 3 }, (_, i) => <SkeletonRow key={i} />)
              : items.map((item) => (
                  <ReportRow
                    key={item.id}
                    item={item}
                    onRowClick={onRowClick}
                    onDelete={onDelete}
                    lang={lang}
                    t={t}
                  />
                ))}
          </tbody>
          {/* Pie con botín acumulado */}
          {!loading && cumulativeBounty != null && items.length > 0 && (
            <tfoot>
              <tr style={{ borderTop: '1px solid var(--border)' }}>
                <td
                  colSpan={6}
                  style={{ padding: '8px 12px', fontSize: '12px', color: 'var(--text-secondary)', textAlign: 'end' }}
                >
                  {t('ar.history.accum').replace('{n}', new Intl.NumberFormat(lang).format(Math.round(cumulativeBounty)))}
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* ── Tarjetas (< md) ──────────────────────────────────────── */}
      <div className="md:hidden" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {loading
          ? Array.from({ length: 3 }, (_, i) => (
              <div key={i} style={{ height: '70px', background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)', animation: 'pulse 1.4s ease-in-out infinite' }} />
            ))
          : items.map((item) => (
              <ReportCard
                key={item.id}
                item={item}
                onRowClick={onRowClick}
                onDelete={onDelete}
                lang={lang}
                t={t}
              />
            ))}
        {/* Botín acumulado en móvil como resumen */}
        {!loading && cumulativeBounty != null && items.length > 0 && (
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', textAlign: 'end', paddingTop: '4px' }}>
            {t('ar.history.accum').replace('{n}', new Intl.NumberFormat(lang).format(Math.round(cumulativeBounty)))}
          </div>
        )}
      </div>

      {/* ── Paginación ────────────────────────────────────────────── */}
      {total > pageSize && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            gap: '12px',
            paddingTop: '8px',
          }}
        >
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: page <= 1 ? 'not-allowed' : 'pointer',
              color: page <= 1 ? 'var(--text-disabled)' : 'var(--text-secondary)',
              fontSize: '13px',
              fontFamily: 'inherit',
              padding: '4px 0',
            }}
          >
            {t('ar.history.prev')}
          </button>
          <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
            {t('ar.history.page').replace('{from}', from).replace('{to}', to).replace('{total}', total)}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: page >= totalPages ? 'not-allowed' : 'pointer',
              color: page >= totalPages ? 'var(--text-disabled)' : 'var(--text-secondary)',
              fontSize: '13px',
              fontFamily: 'inherit',
              padding: '4px 0',
            }}
          >
            {t('ar.history.next')}
          </button>
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.5; }
        }
      `}</style>
    </div>
  )
}
