/**
 * HistoryTab — Pestaña "Historial" del módulo de reportes de oasis.
 *
 * Gestiona estado de carga, filtros, paginación y apertura del drawer.
 *
 * Props:
 *   onOpenDrawer — (id: number) => void
 *   lang         — string
 *   onSwitchTab  — (tabId) => void  (para CTA "Ir a Ingresar")
 */
import { useState, useEffect, useCallback } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api } from '../../api/client.js'
import { HistoryFilters } from './HistoryFilters.jsx'
import { HistoryTable } from './HistoryTable.jsx'
import { Spinner } from '../ui/uiUtils.jsx'

const PAGE_SIZE = 50

const EMPTY_FILTERS = { x: '', y: '', from_date: '', to_date: '' }

function hasFilters(f) {
  return !!(f.x || f.y || f.from_date || f.to_date)
}

export function HistoryTab({ onOpenDrawer, lang, onSwitchTab }) {
  const { t } = useI18n()
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [items, setItems]     = useState([])
  const [total, setTotal]     = useState(0)
  const [cumulativeBounty, setCumulativeBounty] = useState(null)
  const [page, setPage]       = useState(1)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS)

  const load = useCallback(async (pageNum, f) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (f.x)         params.set('x', f.x)
      if (f.y)         params.set('y', f.y)
      if (f.from_date) params.set('from_date', f.from_date)
      if (f.to_date)   params.set('to_date', f.to_date)
      params.set('limit', PAGE_SIZE)
      params.set('offset', (pageNum - 1) * PAGE_SIZE)
      const data = await api.getAttackReports(params.toString())
      setItems(data.items ?? [])
      setTotal(data.total ?? 0)
      setCumulativeBounty(data.cumulative_bounty ?? null)
    } catch (err) {
      setError(err?.detail ?? t('ar.history.error'))
    } finally {
      setLoading(false)
    }
  }, [t])

  // Carga inicial
  useEffect(() => {
    load(1, EMPTY_FILTERS)
  }, [load])

  function handleApplyFilters() {
    setPage(1)
    setAppliedFilters(filters)
    load(1, filters)
  }

  function handleClearFilters() {
    const empty = EMPTY_FILTERS
    setFilters(empty)
    setAppliedFilters(empty)
    setPage(1)
    load(1, empty)
  }

  function handlePageChange(newPage) {
    setPage(newPage)
    load(newPage, appliedFilters)
  }

  async function handleDelete(id) {
    await api.deleteAttackReport(id)
    // Recargar la página actual (puede que el total baje y la paginación cambie)
    const newPage = items.length === 1 && page > 1 ? page - 1 : page
    setPage(newPage)
    await load(newPage, appliedFilters)
  }

  const isFiltered = hasFilters(appliedFilters)
  const isEmpty    = !loading && !error && items.length === 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Filtros */}
      <HistoryFilters
        filters={filters}
        onChange={setFilters}
        onApply={handleApplyFilters}
        onClear={handleClearFilters}
        isFiltered={isFiltered}
      />

      {/* Error */}
      {error && (
        <div
          role="alert"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '12px 14px',
            background: 'var(--danger-subtle, color-mix(in srgb, var(--danger) 10%, transparent))',
            border: '1px solid var(--danger)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
          }}
        >
          <span style={{ color: 'var(--danger)', fontWeight: 700 }}>✕</span>
          <span style={{ flex: 1 }}>{error}</span>
          <button
            type="button"
            onClick={() => load(page, appliedFilters)}
            style={{
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
            {t('ar.history.retry')}
          </button>
        </div>
      )}

      {/* Estado vacío sin filtros */}
      {isEmpty && !isFiltered && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '12px',
            padding: '48px 24px',
            color: 'var(--text-secondary)',
            textAlign: 'center',
          }}
        >
          <span aria-hidden="true" style={{ fontSize: '40px' }}>🐀</span>
          <div>
            <p style={{ margin: 0, fontSize: '15px', fontWeight: 500, color: 'var(--text)' }}>
              {t('ar.history.empty.title')}
            </p>
            <p style={{ margin: '4px 0 0', fontSize: '13px' }}>
              {t('ar.history.empty.desc')}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onSwitchTab('ingest')}
            style={{
              background: 'var(--btn-primary-bg)',
              color: 'var(--btn-primary-text)',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              padding: '8px 16px',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            {t('ar.history.empty.cta')}
          </button>
        </div>
      )}

      {/* Estado vacío con filtros activos */}
      {isEmpty && isFiltered && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '12px',
            padding: '32px 24px',
            textAlign: 'center',
          }}
        >
          <p style={{ margin: 0, fontSize: '14px', color: 'var(--text-secondary)' }}>
            {t('ar.history.filtered.empty')}
          </p>
          <button
            type="button"
            onClick={handleClearFilters}
            style={{
              background: 'transparent',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '6px 14px',
              fontSize: '13px',
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            {t('ar.history.filtered.clear')}
          </button>
        </div>
      )}

      {/* Tabla (con datos o skeleton durante carga) */}
      {!error && (loading || items.length > 0) && (
        <HistoryTable
          items={items}
          total={total}
          page={page}
          pageSize={PAGE_SIZE}
          onPageChange={handlePageChange}
          onRowClick={onOpenDrawer}
          onDelete={handleDelete}
          cumulativeBounty={cumulativeBounty}
          lang={lang}
          loading={loading}
        />
      )}
    </div>
  )
}
