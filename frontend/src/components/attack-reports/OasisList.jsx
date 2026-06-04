/**
 * OasisList — Tabla navegable de oasis con expand-in-place.
 *
 * Carga EP-08 GET /attack-reports/oasis al montar.
 * Al hacer clic en una fila, carga EP-06 GET /attack-reports/stats/oasis?x=&y=
 * y despliega el panel de detalle (OasisStatsPanel) en la misma fila.
 *
 * Estados implementados (spec §7 y §12):
 *  - Cargando lista: skeleton de 3 filas
 *  - Lista con oasis (ninguno expandido)
 *  - Fila expandida — cargando detalle (spinner)
 *  - Fila expandida — con detalle (OasisStatsPanel)
 *  - Fila expandida — error detalle (mensaje + reintentar)
 *  - Lista vacía (sin oasis): estado vacío con CTA "Ir a Ingresar"
 *  - Error carga lista: banner + reintentar
 *  - Filtro activo con resultados
 *  - Filtro activo sin resultados
 *  - Filtro inválido (x sin y): validación inline
 *
 * Accesibilidad (spec §10):
 *  - role="table" en tabla, scope="col" en cabeceras
 *  - aria-expanded + aria-controls en filas expandibles
 *  - Navegación por teclado: Tab + Enter/Space para expandir, Escape colapsa
 *  - Fieldset con legend en filtro de coordenadas
 *  - role="alert" en errores de validación y carga
 *  - Reducción de movimiento respetada
 *
 * Responsive (spec §11):
 *  - < md: tarjetas apiladas (coords, ataques, último ataque); botín oculto
 *  - md+: tabla completa con botín total
 *
 * Props:
 *   lang         — string (idioma activo)
 *   onGoToIngest — () => void (CTA estado vacío → pestaña Ingresar)
 *   t            — función de traducción
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../../api/client.js'
import { Spinner } from '../ui/uiUtils.jsx'
import { OasisStatsPanel } from './OasisStatsPanel.jsx'
import { formatDateVerbatim } from '../../utils/formatDateVerbatim.js'
import { formatCoord, formatCoordSingle } from '../../utils/coordUtils.js'

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatCoordsDisplay(x, y) {
  return formatCoord(x, y)
}

// Formatea la fecha verbatim del último ataque (hora Travian, sin zona)
function formatLastAttack(isoStr) {
  return formatDateVerbatim(isoStr)
}

// ── Tarjeta de un oasis (una por coordenada, todos los tamaños) ───────────────

function OasisCard({ item, isSelected, onToggle, lang, t }) {
  const coordStr = formatCoordsDisplay(item.coord_x_dest, item.coord_y_dest)
  const dateStr  = formatLastAttack(item.last_attack)

  return (
    <div
      style={{
        border: `1px solid ${isSelected ? 'var(--accent)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-sm)',
        background: isSelected ? 'var(--accent-subtle)' : 'var(--surface)',
        overflow: 'hidden',
        transition: 'background var(--dur-fast)',
      }}
    >
      <button
        type="button"
        aria-expanded={isSelected}
        aria-controls={`oasis-detail-${item.coord_x_dest}-${item.coord_y_dest}`}
        onClick={onToggle}
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          width: '100%',
          padding: '10px 12px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'start',
          minHeight: '44px',
          fontFamily: 'inherit',
        }}
      >
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, color: 'var(--text)', fontSize: '14px' }}>
            {coordStr}
          </span>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <span>{t('ar.stats.list.col.attacks')}: <strong>{item.attack_count}</strong></span>
            <span>{dateStr}</span>
          </div>
        </div>
        <span
          aria-hidden="true"
          style={{
            color: isSelected ? 'var(--accent-text)' : 'var(--text-tertiary)',
            fontSize: '12px',
            transform: isSelected ? 'rotate(0deg)' : 'rotate(-90deg)',
            transition: 'transform var(--dur-fast), color var(--dur-fast)',
            flexShrink: 0,
            marginInlineStart: '8px',
          }}
        >
          ▼
        </span>
      </button>
    </div>
  )
}

// ── Componente principal ──────────────────────────────────────────────────────

export function OasisList({ lang, onGoToIngest, t }) {
  // ── Estado de la lista ───────────────────────────────────────────────────
  const [listLoading, setListLoading]   = useState(true)
  const [listError, setListError]       = useState(null)
  const [oasisItems, setOasisItems]     = useState([])

  // ── Estado del filtro ────────────────────────────────────────────────────
  const [filterX, setFilterX]           = useState('')
  const [filterY, setFilterY]           = useState('')
  const [filterValidation, setFilterValidation] = useState(null) // error de validación inline
  const filterDebounceRef               = useRef(null)

  // ── Estado del expand ────────────────────────────────────────────────────
  const [selectedKey, setSelectedKey]   = useState(null) // "x,y" de la fila expandida
  const [detailData, setDetailData]     = useState({})   // { "x,y": { loading, error, data } }
  const selectedRowRef                  = useRef(null)

  // ── Carga inicial ────────────────────────────────────────────────────────
  const loadList = useCallback(async () => {
    setListLoading(true)
    setListError(null)
    try {
      const res = await api.listOasisSummaries()
      setOasisItems(res.items ?? [])
    } catch (err) {
      setListError(err?.detail ?? t('ar.stats.list.error'))
    } finally {
      setListLoading(false)
    }
  }, [t])

  useEffect(() => { loadList() }, [loadList])

  // ── Filtro local ─────────────────────────────────────────────────────────
  // Filtrado en cliente: la lista completa ya está en memoria (sin paginación v1)
  const filteredItems = (() => {
    const xVal = filterX.trim()
    const yVal = filterY.trim()
    if (!xVal && !yVal) return oasisItems
    if (xVal && !yVal) return oasisItems // validación pendiente — se muestra inline
    if (!xVal && yVal) return oasisItems
    const xi = parseInt(xVal, 10)
    const yi = parseInt(yVal, 10)
    if (isNaN(xi) || isNaN(yi)) return oasisItems
    return oasisItems.filter(
      (o) => o.coord_x_dest === xi && o.coord_y_dest === yi
    )
  })()

  // ¿Hay filtro activo (ambos campos tienen valor)?
  const xVal = filterX.trim()
  const yVal = filterY.trim()
  const filterActive = xVal !== '' && yVal !== ''
  const filterPartial = (xVal !== '' && yVal === '') || (xVal === '' && yVal !== '')

  // ── Handlers de filtro ───────────────────────────────────────────────────
  function handleFilterChange(field, value) {
    if (field === 'x') setFilterX(value)
    else setFilterY(value)
    setFilterValidation(null)
  }

  function handleFilterKeyDown(e) {
    if (e.key === 'Enter') {
      const xv = filterX.trim()
      const yv = filterY.trim()
      if (xv && !yv) {
        setFilterValidation(t('ar.stats.list.filter.hint'))
      }
    }
  }

  function handleClearFilter() {
    setFilterX('')
    setFilterY('')
    setFilterValidation(null)
  }

  // ── Handlers de fila ─────────────────────────────────────────────────────
  function oasisKey(item) {
    return `${item.coord_x_dest},${item.coord_y_dest}`
  }

  async function handleRowToggle(item) {
    const key = oasisKey(item)
    if (selectedKey === key) {
      // Colapsar
      setSelectedKey(null)
      return
    }
    // Expandir
    setSelectedKey(key)
    // Si ya tenemos datos para este oasis, no recargar
    if (detailData[key]?.data) return

    // Marcar como cargando
    setDetailData((prev) => ({ ...prev, [key]: { loading: true, error: null, data: null } }))
    try {
      const res = await api.getOasisStats(item.coord_x_dest, item.coord_y_dest)
      setDetailData((prev) => ({ ...prev, [key]: { loading: false, error: null, data: res } }))
    } catch (err) {
      setDetailData((prev) => ({
        ...prev,
        [key]: { loading: false, error: err?.detail ?? t('ar.stats.detail.error'), data: null },
      }))
    }
  }

  async function handleRetryDetail(item) {
    const key = oasisKey(item)
    setDetailData((prev) => ({ ...prev, [key]: { loading: true, error: null, data: null } }))
    try {
      const res = await api.getOasisStats(item.coord_x_dest, item.coord_y_dest)
      setDetailData((prev) => ({ ...prev, [key]: { loading: false, error: null, data: res } }))
    } catch (err) {
      setDetailData((prev) => ({
        ...prev,
        [key]: { loading: false, error: err?.detail ?? t('ar.stats.detail.error'), data: null },
      }))
    }
  }

  // Escape colapsa el panel expandido (foco vuelve a la fila)
  useEffect(() => {
    function handler(e) {
      if (e.key === 'Escape' && selectedKey) {
        setSelectedKey(null)
        selectedRowRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [selectedKey])

  // ── Estado de carga de la lista ──────────────────────────────────────────
  if (listLoading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {/* Filtro deshabilitado durante la carga */}
        <fieldset
          style={{ border: 'none', margin: 0, padding: 0 }}
          disabled
          aria-hidden="true"
        >
          <legend style={{ display: 'none' }}>{t('ar.stats.list.filter.legend')}</legend>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '8px', padding: '12px 0', opacity: 0.5 }}>
            <FilterField label="x" value="" onChange={() => {}} disabled />
            <FilterField label="y" value="" onChange={() => {}} disabled />
          </div>
        </fieldset>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              aria-hidden="true"
              style={{
                height: '64px',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)',
                display: 'flex',
                alignItems: 'center',
                padding: '0 12px',
              }}
            >
              <div style={{ height: '14px', width: `${90 - i * 12}px`, borderRadius: '4px', backgroundImage: 'linear-gradient(90deg,var(--surface-2) 25%,var(--border) 50%,var(--surface-2) 75%)', backgroundSize: '200% 100%', animation: 'shimmer 1.4s infinite' }} />
            </div>
          ))}
        </div>
        <style>{skeletonStyles}</style>
      </div>
    )
  }

  // ── Error de carga ────────────────────────────────────────────────────────
  if (listError) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div
          role="alert"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '12px 14px',
            background: 'var(--danger-subtle, rgba(201,53,44,.08))',
            border: '1px solid var(--danger)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
          }}
        >
          <span style={{ color: 'var(--danger)', fontWeight: 700, flexShrink: 0 }}>✕</span>
          <span style={{ flex: 1 }}>{listError}</span>
          <button
            type="button"
            onClick={loadList}
            style={{
              background: 'var(--btn-primary-bg)',
              color: 'var(--btn-primary-text)',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              padding: '4px 10px',
              fontSize: '12px',
              cursor: 'pointer',
              fontFamily: 'inherit',
              flexShrink: 0,
            }}
          >
            {t('ar.stats.list.retry')}
          </button>
        </div>
      </div>
    )
  }

  // ── Lista vacía (sin oasis en BD) ─────────────────────────────────────────
  if (oasisItems.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
          padding: '48px 24px',
          textAlign: 'center',
        }}
      >
        <span aria-hidden="true" style={{ fontSize: '32px', color: 'var(--text-tertiary)', opacity: 0.6 }}>🐀</span>
        <p style={{ margin: 0, fontSize: '15px', fontWeight: 500, color: 'var(--text)' }}>
          {t('ar.stats.list.empty.title')}
        </p>
        <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary)' }}>
          {t('ar.stats.list.empty.sub')}
        </p>
        <button
          type="button"
          onClick={onGoToIngest}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '0 14px',
            height: '34px',
            background: 'none',
            border: 'none',
            color: 'var(--accent-text)',
            fontSize: '13px',
            cursor: 'pointer',
            fontFamily: 'inherit',
            borderRadius: 'var(--radius-sm)',
            transition: 'background var(--dur-fast)',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--accent-subtle)' }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'none' }}
        >
          {t('ar.stats.list.empty.cta')}
        </button>
      </div>
    )
  }

  // ── Lista con oasis ───────────────────────────────────────────────────────

  // Contador: si hay filtro activo, muestra "N resultado(s)"; si no, total
  const countLabel = (() => {
    if (filterActive && filteredItems.length === 0) return null
    if (filterActive) {
      return filteredItems.length === 1
        ? t('ar.stats.list.count.filtered.one')
        : t('ar.stats.list.count.filtered.pl').replace('{n}', filteredItems.length)
    }
    return oasisItems.length === 1
      ? t('ar.stats.list.count.one')
      : t('ar.stats.list.count.pl').replace('{n}', oasisItems.length)
  })()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
      {/* Encabezado + contador */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', marginBottom: '16px' }}>
        <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text)' }}>
          {t('ar.stats.title')}
        </h2>
        {countLabel && (
          <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>{countLabel}</span>
        )}
      </div>

      {/* Filtro inline */}
      <fieldset
        style={{
          border: 'none',
          margin: '0 0 12px 0',
          padding: 0,
        }}
      >
        <legend style={{
          fontSize: '11px',
          fontWeight: 600,
          color: 'var(--text-tertiary)',
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          marginBottom: '6px',
        }}>
          {t('ar.stats.list.filter.legend')}
        </legend>
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: '8px',
            padding: '12px 16px',
            background: 'var(--surface)',
            border: `1px solid ${filterActive ? 'var(--accent-subtle-border, rgba(138,100,24,.40))' : 'var(--border)'}`,
            borderRadius: 'var(--radius-sm)',
          }}
        >
          <FilterField
            label="x"
            value={filterX}
            onChange={(v) => handleFilterChange('x', v)}
            onKeyDown={handleFilterKeyDown}
            active={filterX.trim() !== ''}
          />
          <FilterField
            label="y"
            value={filterY}
            onChange={(v) => handleFilterChange('y', v)}
            onKeyDown={handleFilterKeyDown}
            active={filterY.trim() !== ''}
          />
          <button
            type="button"
            onClick={handleClearFilter}
            disabled={!filterX && !filterY}
            style={{
              height: '32px',
              padding: '0 12px',
              background: 'none',
              border: 'none',
              color: (filterX || filterY) ? 'var(--accent-text)' : 'var(--text-disabled)',
              fontSize: '13px',
              cursor: (filterX || filterY) ? 'pointer' : 'default',
              fontFamily: 'inherit',
              borderRadius: 'var(--radius-sm)',
              transition: 'background var(--dur-fast)',
            }}
            onMouseEnter={(e) => { if (filterX || filterY) e.currentTarget.style.background = 'var(--accent-subtle)' }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'none' }}
          >
            {t('ar.stats.list.filter.clear')}
          </button>
        </div>
        {/* Validación inline: x sin y */}
        {filterPartial && (
          <p
            role="alert"
            style={{ margin: '6px 0 0 0', fontSize: '12px', color: 'var(--text-tertiary)', paddingInlineStart: '16px' }}
          >
            {t('ar.stats.list.filter.hint')}
          </p>
        )}
      </fieldset>

      {/* Sin resultados de filtro */}
      {filterActive && filteredItems.length === 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '24px 16px', fontSize: '13px', color: 'var(--text-secondary)' }}>
          <span>
            {t('ar.stats.list.filter.noResults')
              .replace('{x}', formatCoordSingle(parseInt(filterX, 10)))
              .replace('{y}', formatCoordSingle(parseInt(filterY, 10)))}
          </span>
          <button
            type="button"
            onClick={handleClearFilter}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--accent-text)',
              fontSize: '13px',
              cursor: 'pointer',
              fontFamily: 'inherit',
              padding: '0 6px',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            {t('ar.stats.list.filter.clearAll')}
          </button>
        </div>
      )}

      {/* ── Tarjetas (una por coordenada, en todos los tamaños) ──────────── */}
      {filteredItems.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {filteredItems.map((item) => {
            const key = oasisKey(item)
            const isSel = selectedKey === key
            const det = detailData[key] ?? {}
            const detailId = `oasis-detail-${item.coord_x_dest}-${item.coord_y_dest}`

            return (
              <div key={key}>
                <OasisCard
                  item={item}
                  isSelected={isSel}
                  onToggle={() => handleRowToggle(item)}
                  lang={lang}
                  t={t}
                />
                {/* Panel expandido: detalle agregado del oasis */}
                {isSel && (
                  <div
                    id={detailId}
                    role="region"
                    aria-label={`${t('ar.stats.detail.region')} ${formatCoordsDisplay(item.coord_x_dest, item.coord_y_dest)}`}
                    style={{
                      padding: '16px',
                      background: 'var(--surface-2)',
                      border: '1px solid var(--border)',
                      borderTop: 'none',
                      borderRadius: '0 0 var(--radius-sm) var(--radius-sm)',
                    }}
                  >
                    {det.loading && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-tertiary)', fontSize: '13px' }}>
                        <Spinner size={16} />
                        {t('ar.stats.detail.loading')}
                      </div>
                    )}
                    {det.error && (
                      <div role="alert" style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '13px' }}>
                        <span style={{ color: 'var(--danger)', fontWeight: 700 }}>✕</span>
                        <span style={{ flex: 1 }}>{det.error}</span>
                        <button type="button" onClick={() => handleRetryDetail(item)} style={{ background: 'var(--btn-primary-bg)', color: 'var(--btn-primary-text)', border: 'none', borderRadius: 'var(--radius-sm)', padding: '4px 10px', fontSize: '12px', cursor: 'pointer', fontFamily: 'inherit' }}>
                          {t('ar.stats.detail.retry')}
                        </button>
                      </div>
                    )}
                    {det.data && !det.loading && (
                      <OasisStatsPanel data={det.data} lang={lang} />
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <style>{`
        @keyframes shimmer {
          0%   { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          [style*="shimmer"] { animation: none !important; }
        }
      `}</style>
    </div>
  )
}

// ── Sub-componentes auxiliares ────────────────────────────────────────────────

function FilterField({ label, value, onChange, onKeyDown, disabled, active }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label
        style={{
          fontSize: '11px',
          color: 'var(--text-tertiary)',
          fontWeight: 500,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
        }}
      >
        {label}
      </label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        placeholder={label}
        style={{
          height: '32px',
          width: '72px',
          padding: '0 10px',
          background: 'var(--surface-2)',
          border: `1px solid ${active ? 'var(--accent)' : 'var(--border-strong)'}`,
          borderRadius: 'var(--radius-sm)',
          fontSize: '13px',
          fontFamily: 'var(--font-mono)',
          color: 'var(--text)',
          outline: 'none',
        }}
        onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '1px' }}
        onBlur={(e) => { e.currentTarget.style.borderColor = active ? 'var(--accent)' : 'var(--border-strong)'; e.currentTarget.style.outline = 'none' }}
      />
    </div>
  )
}

const skeletonStyles = `
  @keyframes shimmer {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
`
