/**
 * NoiseDestinationsTable — Tabla densa de destinos de navegación + filtros + formulario inline.
 *
 * Props:
 *  - worldId         {number}
 *  - destinations    {Array}
 *  - loading         {boolean}
 *  - onOpenDrawer    {Function(dest)} — abre el drawer del destino
 *  - onDeleted       {Function(id)}   — callback tras borrar exitosamente
 *  - onCreated       {Function(dest)} — callback tras crear exitosamente
 *
 * Spec: docs/design/noise-catalog-ui.md §6, §7
 */
import { useState, useRef, memo } from 'react'
import { useI18n } from '../../../i18n/index.jsx'
import { api, ApiError } from '../../../api/client.js'
import { Spinner, showToast } from '../../ui/uiUtils.jsx'
import { ConfirmDeleteModal } from '../../ui/ConfirmDeleteModal.jsx'

// ── Constantes ────────────────────────────────────────────────────────────────

const CATEGORIES = ['MAP', 'OASIS_INFO', 'PLAYER_PROFILE', 'MESSAGES', 'REPORTS', 'BUILDING_VIEW', 'OTHER']

// Mapa de colores de categoría según spec §8
const CATEGORY_STYLE = {
  MAP:            { bg: 'var(--info-subtle)',    color: 'var(--info)' },
  OASIS_INFO:     { bg: 'rgba(36,138,61,.10)',   color: 'var(--success)' },
  PLAYER_PROFILE: { bg: 'var(--accent-subtle)',  color: 'var(--accent-text)' },
  MESSAGES:       { bg: 'var(--mode-idle-subtle, rgba(36,138,61,.07))', color: 'var(--mode-idle, var(--success))' },
  REPORTS:        { bg: 'var(--surface-2)',      color: 'var(--text-secondary)' },
  BUILDING_VIEW:  { bg: 'var(--surface-2)',      color: 'var(--text-secondary)' },
  OTHER:          { bg: 'var(--surface-2)',      color: 'var(--text-tertiary)' },
}

// ── Icono ─────────────────────────────────────────────────────────────────────

function IconTrash({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14H6L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4h6v2" />
    </svg>
  )
}

function IconWarning({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

// ── NoiseCategoryBadge ────────────────────────────────────────────────────────

export function NoiseCategoryBadge({ category }) {
  const { t } = useI18n()
  const s = CATEGORY_STYLE[category] ?? CATEGORY_STYLE.OTHER
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      borderRadius: 'var(--radius-full)',
      padding: '2px 8px',
      fontSize: '11px', fontWeight: 500,
      letterSpacing: '0.03em',
      background: s.bg, color: s.color,
      whiteSpace: 'nowrap',
    }}>
      {t(`noise.category.${category}`) ?? category}
    </span>
  )
}

// ── SkeletonTable ─────────────────────────────────────────────────────────────

function SkeletonTable() {
  const pulse = {
    background: 'var(--surface-2)',
    borderRadius: 'var(--radius-sm)',
    animation: 'skeleton-pulse 1.4s ease-in-out infinite',
  }
  return (
    <>
      <style>{`@keyframes skeleton-pulse{0%,100%{opacity:1}50%{opacity:.45}}`}</style>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <tbody>
          {[1, 2, 3].map(i => (
            <tr key={i}>
              {[180, 80, 40, 30, 40].map((w, j) => (
                <td key={j} style={{ padding: '12px 8px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ ...pulse, height: '13px', width: `${w}px` }} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

// ── NoiseAddDestinationForm ───────────────────────────────────────────────────

function NoiseAddDestinationForm({ worldId, onCreated, onCancel }) {
  const { t } = useI18n()
  const [form, setForm] = useState({
    url_pattern: '',
    label: '',
    category: 'MAP',
    navigation_weight: 1.0,
    is_safe: true,
  })
  const [creating, setCreating] = useState(false)
  const [urlError, setUrlError] = useState(null)
  const urlRef = useRef(null)

  const isValid = form.url_pattern.trim().length > 0 && form.navigation_weight > 0

  async function handleCreate() {
    if (!isValid || creating) return
    setCreating(true)
    setUrlError(null)
    try {
      const created = await api.createNoiseDestination(worldId, form)
      showToast(t('noise.form.created'))
      onCreated(created)
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 422) {
          setUrlError(e.detail)
        } else {
          showToast(e.detail)
        }
      } else {
        showToast(t('noise.error.loadFailed'))
      }
    } finally {
      setCreating(false)
    }
  }

  return (
    <div style={{
      background: 'var(--surface-2)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      padding: '14px',
      marginBottom: '12px',
      animation: 'form-expand 200ms ease',
    }}>
      <style>{`@keyframes form-expand{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}`}</style>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '12px', marginBottom: '12px' }}>
        {/* URL */}
        <div>
          <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', fontWeight: 500 }}>
            {t('noise.form.urlPattern')}
          </label>
          <input
            ref={urlRef}
            type="text"
            value={form.url_pattern}
            placeholder="/karte.php"
            autoFocus
            onChange={e => { setForm(f => ({ ...f, url_pattern: e.target.value })); setUrlError(null) }}
            style={{
              width: '100%', padding: '6px 8px',
              border: `1px solid ${urlError ? 'var(--danger)' : 'var(--border-strong)'}`,
              borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: 'var(--text)',
              fontFamily: 'var(--font-mono)', fontSize: '13px',
              boxSizing: 'border-box',
            }}
            aria-describedby={urlError ? 'url-err' : undefined}
          />
          {urlError && <span id="url-err" role="alert" style={{ fontSize: '11px', color: 'var(--danger)', display: 'block', marginTop: '3px' }}>{urlError}</span>}
        </div>

        {/* Label */}
        <div>
          <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', fontWeight: 500 }}>
            {t('noise.form.label')}
          </label>
          <input
            type="text"
            value={form.label}
            onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
            style={{
              width: '100%', padding: '6px 8px',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: 'var(--text)',
              fontFamily: 'inherit', fontSize: '13px',
              boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Categoría */}
        <div>
          <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', fontWeight: 500 }}>
            {t('noise.form.category')}
          </label>
          <select
            value={form.category}
            onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
            style={{
              width: '100%', padding: '6px 8px',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: 'var(--text)',
              fontFamily: 'inherit', fontSize: '13px',
              cursor: 'pointer',
            }}
          >
            {CATEGORIES.map(c => (
              <option key={c} value={c}>{t(`noise.category.${c}`) ?? c}</option>
            ))}
          </select>
        </div>

        {/* Peso */}
        <div>
          <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', fontWeight: 500 }}>
            {t('noise.form.weight')}
          </label>
          <input
            type="number"
            min="0.1"
            max="5"
            step="0.1"
            value={form.navigation_weight}
            onChange={e => setForm(f => ({ ...f, navigation_weight: parseFloat(e.target.value) || 1.0 }))}
            style={{
              width: '80px', padding: '6px 8px',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: 'var(--text)',
              fontFamily: 'var(--font-mono)', fontSize: '13px',
            }}
          />
        </div>

        {/* is_safe */}
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '8px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '13px' }}>
            <input
              type="checkbox"
              checked={form.is_safe}
              onChange={e => setForm(f => ({ ...f, is_safe: e.target.checked }))}
              style={{ width: '16px', height: '16px', cursor: 'pointer' }}
            />
            {t('noise.form.safe')}
          </label>
        </div>
      </div>

      {/* Footer */}
      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
        <button
          type="button"
          onClick={onCancel}
          style={{
            height: '32px', padding: '0 14px',
            border: '1px solid var(--border-strong)',
            background: 'var(--surface)', color: 'var(--text-secondary)',
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'inherit', fontSize: '13px',
            cursor: 'pointer',
          }}
        >
          {t('noise.form.cancel')}
        </button>
        <button
          type="button"
          onClick={handleCreate}
          disabled={!isValid || creating}
          style={{
            height: '32px', padding: '0 14px',
            border: 'none',
            background: (!isValid || creating) ? 'var(--surface-2)' : 'var(--btn-primary-bg)',
            color: (!isValid || creating) ? 'var(--text-disabled)' : 'var(--btn-primary-text)',
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
            cursor: (!isValid || creating) ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', gap: '6px',
          }}
        >
          {creating && <Spinner size={12} />}
          {creating ? t('noise.form.creating') : t('noise.form.create')}
        </button>
      </div>
    </div>
  )
}

// ── NoiseDestinationsTable ────────────────────────────────────────────────────

// React.memo: evita re-render cuando NoiseTab re-renderiza por cambio de estado del drawer.
// Precondición: NoiseTab debe pasar onOpenDrawer/onDeleted/onCreated estables (useCallback).
//
// Props adicionales (retrocompatibles):
//  - mode         {"world"|"template"} — en "template" oculta el form de creación y el filtro de muertos.
//  - onDeleteItem {Function(destId)}   — reemplaza el handler de borrado interno (para modo template).
export const NoiseDestinationsTable = memo(function NoiseDestinationsTable({
  worldId, destinations, loading, onOpenDrawer, onDeleted, onCreated,
  mode = 'world',
  onDeleteItem,
}) {
  const { t } = useI18n()
  const [showAddForm, setShowAddForm] = useState(false)
  const [filterCategory, setFilterCategory] = useState('')
  const [showDead, setShowDead] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null) // { dest }
  const deleteButtonRefs = useRef({})

  // Filtrado
  const filtered = (destinations ?? []).filter(d => {
    if (!showDead && d.is_dead) return false
    if (filterCategory && d.category !== filterCategory) return false
    return true
  })

  const hiddenDeadCount = (!showDead) ? (destinations ?? []).filter(d => d.is_dead).length : 0

  function handleCreated(dest) {
    setShowAddForm(false)
    onCreated(dest)
  }

  async function handleConfirmDelete() {
    if (!deleteTarget) return
    if (onDeleteItem) {
      await onDeleteItem(deleteTarget.dest.id)
    } else {
      await api.deleteNoiseDestination(worldId, deleteTarget.dest.id)
    }
    showToast(t('noise.destinations.deleted'))
    onDeleted?.(deleteTarget.dest.id)
    setDeleteTarget(null)
  }

  const thStyle = {
    fontSize: '11px', color: 'var(--text-secondary)',
    textTransform: 'uppercase', letterSpacing: '.04em',
    fontWeight: 500, padding: '6px 8px',
    borderBottom: '1px solid var(--border)',
    textAlign: 'start',
    whiteSpace: 'nowrap',
  }

  return (
    <div>
      {/* Título + botón añadir */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px', flexWrap: 'wrap' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, flex: 1, margin: 0 }}>
          {t('noise.destinations.title')}
        </h3>

        {/* Filtro categoría */}
        <select
          value={filterCategory}
          onChange={e => setFilterCategory(e.target.value)}
          style={{
            padding: '5px 8px',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--surface)', color: 'var(--text)',
            fontFamily: 'inherit', fontSize: '12px',
            cursor: 'pointer',
          }}
          aria-label={t('noise.destinations.filterCategory')}
        >
          <option value="">{t('noise.destinations.filterAll')}</option>
          {CATEGORIES.map(c => (
            <option key={c} value={c}>{t(`noise.category.${c}`) ?? c}</option>
          ))}
        </select>

        {/* Filtro muertos — solo en modo world */}
        {mode === 'world' && (
          <label style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '12px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showDead}
              onChange={e => setShowDead(e.target.checked)}
              style={{ width: '14px', height: '14px' }}
            />
            {t('noise.destinations.showDead')}
          </label>
        )}

        {/* Botón añadir — solo en modo world */}
        {mode === 'world' && !showAddForm && (
          <button
            type="button"
            onClick={() => setShowAddForm(true)}
            style={{
              height: '32px', padding: '0 14px',
              border: 'none',
              background: 'var(--btn-primary-bg)',
              color: 'var(--btn-primary-text)',
              borderRadius: 'var(--radius-sm)',
              fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {t('noise.destinations.add')}
          </button>
        )}
      </div>

      {/* Formulario inline de nuevo destino — solo en modo world */}
      {mode === 'world' && showAddForm && (
        <NoiseAddDestinationForm
          worldId={worldId}
          onCreated={handleCreated}
          onCancel={() => setShowAddForm(false)}
        />
      )}

      {/* Aviso de destinos muertos ocultos */}
      {hiddenDeadCount > 0 && (
        <p style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginBottom: '8px' }}>
          {t('noise.destinations.hiddenCount').replace('{n}', hiddenDeadCount)}
        </p>
      )}

      {/* Tabla */}
      {loading ? (
        <SkeletonTable />
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px 24px' }}>
          <p style={{ fontSize: '15px', fontWeight: 600, marginBottom: '8px' }}>
            {filterCategory ? t('noise.destinations.noCategory') : t('noise.destinations.empty')}
          </p>
          {!filterCategory && !showAddForm && (
            <button
              type="button"
              onClick={() => setShowAddForm(true)}
              style={{
                height: '34px', padding: '0 16px',
                border: 'none',
                background: 'var(--btn-primary-bg)',
                color: 'var(--btn-primary-text)',
                borderRadius: 'var(--radius-sm)',
                fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              {t('noise.destinations.emptyCta')}
            </button>
          )}
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }} role="table">
            <thead>
              <tr>
                <th scope="col" style={thStyle}>{t('noise.destinations.col.name')}</th>
                <th scope="col" style={{ ...thStyle, display: 'none' }} className="noise-col-cat">{t('noise.destinations.col.category')}</th>
                <th scope="col" style={{ ...thStyle, textAlign: 'end' }}>{t('noise.destinations.col.weight')}</th>
                <th scope="col" style={{ ...thStyle, display: 'none' }} className="noise-col-safe">{t('noise.destinations.col.safe')}</th>
                <th scope="col" style={{ ...thStyle, textAlign: 'center', display: 'none' }} className="noise-col-paths">{t('noise.destinations.col.paths')}</th>
                <th scope="col" style={{ ...thStyle, width: '32px' }} aria-label="Acciones" />
              </tr>
            </thead>
            <tbody>
              {filtered.map(dest => (
                <DestinationRow
                  key={dest.id}
                  dest={dest}
                  onOpenDrawer={onOpenDrawer}
                  onDelete={() => setDeleteTarget({ dest })}
                  deleteRef={el => { deleteButtonRefs.current[dest.id] = el }}
                  t={t}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Responsive col visibility */}
      <style>{`
        @media (min-width: 640px) {
          .noise-col-cat  { display: table-cell !important; }
          .noise-col-safe { display: table-cell !important; }
        }
        @media (min-width: 900px) {
          .noise-col-paths { display: table-cell !important; }
        }
        .noise-dest-row:hover { background: var(--surface-2); }
      `}</style>

      {/* Modal de confirmación de borrado */}
      {deleteTarget && (
        <ConfirmDeleteModal
          title={t('noise.destinations.col.name')}
          question={t('noise.destinations.deleteConfirm')
            .replace('{label}', deleteTarget.dest.label || deleteTarget.dest.url_pattern)
            .replace('{paths}', deleteTarget.dest.path_count ?? 0)
            .replace('{steps}', deleteTarget.dest.step_count ?? 0)
          }
          warning=""
          onConfirm={handleConfirmDelete}
          onClose={() => setDeleteTarget(null)}
          triggerRef={{ current: deleteButtonRefs.current[deleteTarget.dest.id] }}
        />
      )}
    </div>
  )
})

// ── DestinationRow ────────────────────────────────────────────────────────────

function DestinationRow({ dest, onOpenDrawer, onDelete, deleteRef, t }) {
  const isDead = dest.is_dead === true

  const rowStyle = {
    cursor: 'pointer',
    background: isDead ? 'rgba(201,53,44,.04)' : undefined,
    transition: 'background var(--dur-fast)',
  }

  const tdBase = {
    padding: '10px 8px',
    borderBottom: '1px solid var(--border)',
    verticalAlign: 'middle',
    fontSize: '13px',
  }

  return (
    <tr
      className="noise-dest-row"
      role="row"
      style={rowStyle}
      tabIndex={0}
      onClick={() => onOpenDrawer(dest)}
      onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onOpenDrawer(dest)}
    >
      {/* Nombre / URL */}
      <td role="cell" style={tdBase}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <button
            type="button"
            onClick={() => onOpenDrawer(dest)}
            style={{
              appearance: 'none', border: 'none', background: 'transparent',
              padding: 0, cursor: 'pointer', textAlign: 'start',
              fontFamily: 'inherit',
              display: 'flex', alignItems: 'center', gap: '5px',
            }}
          >
            {isDead && (
              <span style={{ color: 'var(--danger)', flexShrink: 0 }}>
                <IconWarning size={13} />
              </span>
            )}
            <span style={{ fontWeight: 500, color: 'var(--text)' }}>
              {dest.label || dest.url_pattern}
            </span>
          </button>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '11px',
            color: 'var(--text-tertiary)',
          }}>
            {dest.url_pattern}
          </span>
          {isDead && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: '4px',
              fontSize: '11px', fontWeight: 500,
              color: 'var(--danger)',
              background: 'rgba(201,53,44,.08)',
              borderRadius: 'var(--radius-full)',
              padding: '1px 7px',
              width: 'fit-content',
            }}>
              {t('noise.destinations.dead')}
              {dest.consecutive_failures_count > 0 && (
                <span style={{ fontFamily: 'var(--font-mono)' }}>
                  · {t('noise.destinations.deadFails').replace('{n}', dest.consecutive_failures_count)}
                </span>
              )}
            </span>
          )}
        </div>
      </td>

      {/* Categoría */}
      <td role="cell" style={tdBase} className="noise-col-cat">
        <NoiseCategoryBadge category={dest.category} />
      </td>

      {/* Peso */}
      <td role="cell" style={{ ...tdBase, fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', textAlign: 'end' }}>
        {dest.navigation_weight}
      </td>

      {/* Seguro */}
      <td role="cell" style={{ ...tdBase, textAlign: 'center' }} className="noise-col-safe">
        {dest.is_safe ? (
          <span aria-label={t('noise.destinations.safe')} style={{ color: 'var(--success)', fontSize: '15px' }}>✓</span>
        ) : (
          <span aria-label={t('noise.destinations.unsafe')} style={{ color: 'var(--text-tertiary)', fontSize: '15px' }}>✗</span>
        )}
      </td>

      {/* N rutas */}
      <td role="cell" style={{ ...tdBase, textAlign: 'center', fontFamily: 'var(--font-mono)' }} className="noise-col-paths">
        <button
          type="button"
          onClick={() => onOpenDrawer(dest)}
          style={{
            appearance: 'none', border: 'none', background: 'transparent',
            cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: '13px',
            color: (dest.path_count ?? 0) === 0 ? 'var(--text-tertiary)' : 'var(--text)',
            padding: '2px 6px',
          }}
          aria-label={`${dest.path_count ?? 0} rutas de ${dest.label || dest.url_pattern}`}
        >
          {dest.path_count ?? 0}
        </button>
      </td>

      {/* Borrar */}
      <td role="cell" style={{ ...tdBase, width: '32px', textAlign: 'center' }}
        onClick={e => e.stopPropagation()}
        onKeyDown={e => e.stopPropagation()}
      >
        <button
          ref={deleteRef}
          type="button"
          onClick={onDelete}
          aria-label={`Eliminar destino ${dest.label || dest.url_pattern}`}
          style={{
            width: '28px', height: '28px',
            border: 'none', background: 'transparent',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--text-tertiary)',
            transition: 'color var(--dur-fast), background var(--dur-fast)',
          }}
          className="noise-del-btn"
        >
          <IconTrash size={14} />
        </button>
      </td>
    </tr>
  )
}
