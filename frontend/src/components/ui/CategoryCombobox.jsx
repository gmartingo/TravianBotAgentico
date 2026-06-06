/**
 * CategoryCombobox — Desplegable inteligente de categorías de ruta.
 *
 * Spec de diseño: docs/design/route-categories-combobox.md
 * Estado: ready-for-impl / mockup aprobado 2026-06-06
 *
 * Exporta:
 *   - CategoryCombobox (componente principal: CRUD inline)
 *   - CategoryBadge    (badge dinámico readonly que acepta {label, color})
 *   - PALETTE          (12 entradas con name + var CSS)
 *
 * Accesibilidad:
 *   - trigger: role="combobox", aria-haspopup="listbox", aria-expanded, aria-controls
 *   - panel: role="listbox", id="category-listbox-{uid}"
 *   - items: role="option", aria-selected
 *   - input búsqueda: role="searchbox", aria-autocomplete="list"
 *   - ColorSwatchPicker: role="dialog", focus trap
 *   - DeletePopover: focus trap (reutiliza componente existente)
 *   - Todos los targets interactivos ≥ 28px (desktop), ≥ 44px (móvil)
 *
 * Responsive (§11):
 *   - desktop: panel flotante posicionado, acciones solo en hover
 *   - móvil (<768px): bottom sheet + acciones siempre visibles
 *
 * Props de CategoryCombobox:
 *   value        {string|null}   — slug de la categoría seleccionada
 *   onChange     {Function}      — (slug, catObj) => void — llamada al seleccionar
 *   readOnly     {boolean}       — si true, no abre el desplegable (solo muestra badge)
 *   id           {string}        — para aria-controls (opcional, genera uno si no se pasa)
 */

import { useState, useEffect, useRef, useCallback, useId } from 'react'
import { api, ApiError } from '../../api/client.js'
import { Spinner, showToast } from './uiUtils.jsx'
import { DeletePopover } from './DeletePopover.jsx'

// ── Paleta de 12 colores de categoría (§14 del spec) ─────────────────────────

export const PALETTE = [
  { name: 'Acero',         var: '--cat-steel'   },
  { name: 'Musgo',         var: '--cat-moss'    },
  { name: 'Ámbar',         var: '--cat-amber'   },
  { name: 'Terracota',     var: '--cat-terracot'},
  { name: 'Malva',         var: '--cat-mauve'   },
  { name: 'Teal',          var: '--cat-teal'    },
  { name: 'Salmón',        var: '--cat-salmon'  },
  { name: 'Pizarra',       var: '--cat-slate'   },
  { name: 'Índigo',        var: '--cat-indigo'  },
  { name: 'Siena',         var: '--cat-sienna'  },
  { name: 'Bosque',        var: '--cat-forest'  },
  { name: 'Grafito cálido',var: '--cat-warmgra' },
]

// ── CategoryBadge dinámico (exportado para uso en tablas) ─────────────────────

export function CategoryBadge({ label, color, size = 'sm' }) {
  // color puede ser un var(--cat-*) o null
  const hasBg = Boolean(color)
  const style = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    borderRadius: 'var(--radius-full)',
    padding: size === 'sm' ? '2px 8px' : '3px 10px',
    fontSize: '11px',
    fontWeight: 500,
    letterSpacing: '0.03em',
    whiteSpace: 'nowrap',
    background: hasBg ? color : 'var(--surface-2)',
    color: hasBg ? '#FFFFFF' : 'var(--text-secondary)',
  }
  return <span style={style}>{label ?? 'Sin categoría'}</span>
}

// ── Iconos SVG inline ─────────────────────────────────────────────────────────

function IconChevron({ size = 12, up }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true"
      style={{ transform: up ? 'rotate(180deg)' : 'none', transition: 'transform var(--dur-fast)' }}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

function IconPencil({ size = 12 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  )
}

function IconPalette({ size = 12 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="13.5" cy="6.5" r=".5" fill="currentColor" />
      <circle cx="17.5" cy="10.5" r=".5" fill="currentColor" />
      <circle cx="8.5" cy="7.5" r=".5" fill="currentColor" />
      <circle cx="6.5" cy="12.5" r=".5" fill="currentColor" />
      <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z" />
    </svg>
  )
}

function IconTrash({ size = 12 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14H6L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4h6v2" />
    </svg>
  )
}

function IconCheck({ size = 11 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function IconX({ size = 10 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function IconWarning({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

// ── ColorSwatchPicker ──────────────────────────────────────────────────────────

function ColorSwatchPicker({ currentColor, onSelect, onClose, triggerRef }) {
  const dialogRef = useRef(null)

  // Focus trap
  useEffect(() => {
    const prev = document.activeElement
    // Foco al primer swatch al abrir
    setTimeout(() => {
      const first = dialogRef.current?.querySelector('[tabindex="0"], button')
      first?.focus()
    }, 20)
    return () => { prev?.focus() }
  }, [])

  useEffect(() => {
    function handleKey(e) {
      if (e.key === 'Escape') { onClose(); triggerRef?.current?.focus() }
      if (e.key === 'Tab' && dialogRef.current) {
        const focusable = Array.from(dialogRef.current.querySelectorAll('button'))
        if (!focusable.length) return
        const first = focusable[0], last = focusable[focusable.length - 1]
        if (e.shiftKey) {
          if (document.activeElement === first) { e.preventDefault(); last.focus() }
        } else {
          if (document.activeElement === last) { e.preventDefault(); first.focus() }
        }
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose, triggerRef])

  const swatchBtn = (color, label, isActive, onClick) => (
    <button
      key={label}
      type="button"
      title={label}
      aria-label={label + (isActive ? ' (seleccionado)' : '')}
      aria-pressed={isActive}
      onClick={onClick}
      style={{
        width: '24px', height: '24px', minWidth: '24px',
        borderRadius: 'var(--radius-sm)',
        background: color,
        border: isActive
          ? '2px solid var(--accent)'
          : '2px solid transparent',
        cursor: 'pointer',
        padding: 0,
        outline: 'none',
        boxSizing: 'border-box',
        boxShadow: isActive ? '0 0 0 2px var(--surface), 0 0 0 4px var(--accent)' : 'none',
        transition: 'box-shadow var(--dur-fast)',
      }}
      onFocus={e => { e.currentTarget.style.boxShadow = '0 0 0 2px var(--surface), 0 0 0 4px var(--accent)' }}
      onBlur={e => { if (!isActive) e.currentTarget.style.boxShadow = 'none' }}
    />
  )

  return (
    <>
      {/* Overlay invisible para click fuera */}
      <div
        aria-hidden="true"
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, zIndex: 299 }}
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-label="Seleccionar color"
        aria-modal="true"
        style={{
          position: 'absolute',
          insetInlineStart: 0,
          top: '100%',
          marginTop: '4px',
          background: 'var(--surface)',
          border: '1px solid var(--border-strong)',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-lg)',
          padding: '10px',
          zIndex: 300,
          minWidth: '172px',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Grid 6×2 */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 24px)', gap: '6px', marginBottom: '8px' }}>
          {PALETTE.map(({ name, var: cssVar }) => {
            // Resolvemos el color CSS real para usar como fondo del swatch
            const bgColor = `var(${cssVar})`
            const isActive = currentColor === bgColor
            return swatchBtn(bgColor, name, isActive, () => onSelect(bgColor))
          })}
        </div>
        {/* Divisor */}
        <div style={{ borderTop: '1px solid var(--border)', marginBottom: '8px' }} />
        {/* Sin color */}
        <button
          type="button"
          aria-label="Sin color asignado"
          aria-pressed={!currentColor}
          onClick={() => onSelect(null)}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            width: '100%', padding: '2px 4px',
            border: 'none', background: 'transparent',
            cursor: 'pointer', fontSize: '12px',
            color: 'var(--text-secondary)',
            fontFamily: 'inherit',
            outline: 'none',
          }}
        >
          {/* Círculo con borde punteado */}
          <span style={{
            display: 'inline-block', width: '16px', height: '16px',
            border: '2px dashed var(--border-strong)',
            borderRadius: '50%', flexShrink: 0,
            boxSizing: 'border-box',
          }} />
          Sin color
          {!currentColor && (
            <span style={{ marginInlineStart: 'auto', color: 'var(--accent)' }}>
              <IconCheck size={11} />
            </span>
          )}
        </button>
      </div>
    </>
  )
}

// ── CategoryItem — fila de la lista ───────────────────────────────────────────

function CategoryItem({
  cat, isSelected, onSelect,
  onRenameStart,
  isRenaming, renameValue, renameError, onRenameChange, onRenameConfirm, onRenameCancel, renameLoading,
  showSwatchPicker, onSwatchOpen, onSwatchClose, onSwatchSelect, swatchLoading,
  showDeletePop, onDeleteOpen, onDeleteClose, onDeleteConfirm, deleteLoading,
  deletePopTriggerRef,
  isMobile,
}) {
  const [hovered, setHovered] = useState(false)
  const renameInputRef = useRef(null)
  const renameConfirmRef = useRef(null)

  // Al entrar al modo renombrar: autoselect
  useEffect(() => {
    if (isRenaming) {
      setTimeout(() => {
        renameInputRef.current?.select()
        renameInputRef.current?.focus()
      }, 20)
    }
  }, [isRenaming])

  const showActions = hovered || isMobile || isSelected

  const itemStyle = {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '0 10px',
    height: '36px',
    minHeight: isMobile ? '44px' : '36px',
    background: hovered ? 'var(--surface-2)' : 'transparent',
    cursor: 'pointer',
    transition: 'background var(--dur-fast)',
    boxSizing: 'border-box',
  }

  const actionBtnStyle = {
    width: '24px', height: '24px',
    border: 'none', background: 'transparent',
    cursor: 'pointer', padding: 0,
    borderRadius: 'var(--radius-sm)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: 'var(--text-tertiary)',
    flexShrink: 0,
    transition: 'color var(--dur-fast), background var(--dur-fast)',
  }

  // Swatch de color del item
  const swatchEl = (
    <span
      style={{
        display: 'inline-block',
        width: '12px', height: '12px', minWidth: '12px',
        borderRadius: 'var(--radius-sm)',
        background: cat.color ?? undefined,
        border: cat.color ? 'none' : '2px dashed var(--border-strong)',
        boxSizing: 'border-box',
        flexShrink: 0,
      }}
      title={cat.label}
    />
  )

  if (isRenaming) {
    return (
      <div
        style={{ ...itemStyle, flexWrap: 'wrap', height: 'auto', paddingTop: '6px', paddingBottom: '6px', cursor: 'default' }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        role="option"
        aria-selected={isSelected}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', width: '100%' }}>
          {swatchEl}
          <input
            ref={renameInputRef}
            type="text"
            value={renameValue}
            onChange={e => onRenameChange(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') { e.preventDefault(); onRenameConfirm() }
              if (e.key === 'Escape') { e.preventDefault(); onRenameCancel() }
            }}
            style={{
              flex: 1,
              fontSize: '13px',
              padding: '3px 6px',
              border: renameError ? '1px solid var(--danger)' : '1px solid var(--accent)',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--surface-2)',
              color: 'var(--text)',
              fontFamily: 'inherit',
              outline: 'none',
            }}
            aria-label="Nuevo nombre de la categoría"
          />
          {/* Confirmar */}
          <button
            ref={renameConfirmRef}
            type="button"
            onClick={onRenameConfirm}
            disabled={renameLoading || renameValue === cat.label || !renameValue.trim()}
            aria-label="Confirmar renombrado"
            style={{
              ...actionBtnStyle,
              color: renameLoading ? 'var(--text-disabled)' : 'var(--success)',
            }}
          >
            {renameLoading ? <Spinner size={10} /> : <IconCheck size={11} />}
          </button>
          {/* Cancelar */}
          <button
            type="button"
            onClick={onRenameCancel}
            aria-label="Cancelar renombrado"
            style={actionBtnStyle}
          >
            <IconX size={10} />
          </button>
        </div>
        {renameError && (
          <span role="alert" style={{
            fontSize: '11px', color: 'var(--danger)',
            paddingInlineStart: '20px',
            display: 'flex', alignItems: 'center', gap: '3px',
            width: '100%',
          }}>
            ⚠ {renameError}
          </span>
        )}
      </div>
    )
  }

  return (
    <div
      style={itemStyle}
      role="option"
      aria-selected={isSelected}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onSelect(cat)}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(cat) }
      }}
      tabIndex={0}
    >
      {/* Check si está seleccionado */}
      <span style={{
        width: '14px', flexShrink: 0,
        color: 'var(--accent-text)',
        display: 'flex', alignItems: 'center',
        visibility: isSelected ? 'visible' : 'hidden',
      }}>
        <IconCheck size={11} />
      </span>

      {/* Swatch de color */}
      {swatchEl}

      {/* Label */}
      <span style={{
        flex: 1, fontSize: '13px', color: 'var(--text)',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {cat.label}
      </span>

      {/* Acciones (hover/foco/móvil) */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '2px',
        opacity: showActions ? 1 : 0,
        transition: 'opacity 100ms',
        pointerEvents: showActions ? 'auto' : 'none',
      }}>
        {/* Renombrar */}
        <button
          type="button"
          title="Renombrar"
          aria-label="Renombrar"
          onClick={e => { e.stopPropagation(); onRenameStart() }}
          style={actionBtnStyle}
          className="cc-action-btn"
        >
          <IconPencil size={12} />
        </button>

        {/* Color — posición relativa para el picker */}
        <div style={{ position: 'relative' }}>
          <button
            type="button"
            title="Cambiar color"
            aria-label="Cambiar color"
            onClick={e => { e.stopPropagation(); showSwatchPicker ? onSwatchClose() : onSwatchOpen() }}
            style={{
              ...actionBtnStyle,
              opacity: swatchLoading ? 0.5 : 1,
            }}
            disabled={swatchLoading}
            className="cc-action-btn"
          >
            {swatchLoading ? <Spinner size={10} /> : <IconPalette size={12} />}
          </button>
          {showSwatchPicker && (
            <ColorSwatchPicker
              currentColor={cat.color}
              onSelect={onSwatchSelect}
              onClose={onSwatchClose}
              triggerRef={null}
            />
          )}
        </div>

        {/* Borrar — solo si no es la default */}
        {!cat.is_default && (
          <div style={{ position: 'relative' }}>
            <button
              ref={deletePopTriggerRef}
              type="button"
              title="Eliminar categoría"
              aria-label="Eliminar categoría"
              onClick={e => { e.stopPropagation(); showDeletePop ? onDeleteClose() : onDeleteOpen() }}
              style={{ ...actionBtnStyle, color: showDeletePop ? 'var(--danger)' : 'var(--text-tertiary)' }}
              className="cc-action-btn cc-action-btn-danger"
            >
              <IconTrash size={12} />
            </button>
            {showDeletePop && (
              <DeletePopover
                question={`¿Eliminar la categoría "${cat.label}"? Sus rutas pasarán a «Sin categoría».`}
                confirmLabel="Eliminar"
                cancelLabel="Cancelar"
                onConfirm={onDeleteConfirm}
                onCancel={onDeleteClose}
                loading={deleteLoading}
                triggerRef={deletePopTriggerRef}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── CategoryCombobox — contenedor principal ────────────────────────────────────

export function CategoryCombobox({ value, onChange, readOnly = false, id: idProp }) {
  const uid = useId()
  const listboxId = `category-listbox-${idProp ?? uid}`

  // ─── Estado de datos ───────────────────────────────────────────────────────
  const [categories, setCategories] = useState([])
  const [loadingCats, setLoadingCats] = useState(true)
  const [loadError, setLoadError] = useState(null)

  // ─── Estado del desplegable ────────────────────────────────────────────────
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')

  // ─── Estado de mutaciones por item ─────────────────────────────────────────
  const [renamingSlug, setRenamingSlug] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [renameError, setRenameError] = useState(null)
  const [renameLoading, setRenameLoading] = useState(false)

  const [swatchOpenSlug, setSwatchOpenSlug] = useState(null)
  const [swatchLoading, setSwatchLoading] = useState(null) // slug

  const [deleteOpenSlug, setDeleteOpenSlug] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  const [creatingLoading, setCreatingLoading] = useState(false)
  const [createError, setCreateError] = useState(null)

  // ─── Responsive ─────────────────────────────────────────────────────────────
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768)
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])

  // ─── Refs ───────────────────────────────────────────────────────────────────
  const triggerRef = useRef(null)
  const panelRef = useRef(null)
  const searchInputRef = useRef(null)
  const deletePopTriggerRefs = useRef({})

  // ─── Carga de categorías ────────────────────────────────────────────────────

  const loadCategories = useCallback(async () => {
    setLoadingCats(true)
    setLoadError(null)
    try {
      const data = await api.listCategories()
      setCategories(Array.isArray(data) ? data : [])
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.detail : 'Error de red')
    } finally {
      setLoadingCats(false)
    }
  }, [])

  useEffect(() => { loadCategories() }, [loadCategories])

  // ─── Categoría seleccionada ─────────────────────────────────────────────────

  const selectedCat = categories.find(c => c.slug === value) ?? null

  // ─── Abrir / cerrar ─────────────────────────────────────────────────────────

  function openDropdown() {
    if (readOnly || loadingCats || loadError) return
    setOpen(true)
    setSearch('')
    setCreateError(null)
    setTimeout(() => searchInputRef.current?.focus(), 30)
  }

  function closeDropdown() {
    setOpen(false)
    setSearch('')
    setRenamingSlug(null)
    setRenameError(null)
    setSwatchOpenSlug(null)
    setDeleteOpenSlug(null)
    setCreateError(null)
  }

  // Cerrar al hacer click fuera
  useEffect(() => {
    if (!open) return
    function handler(e) {
      if (panelRef.current && !panelRef.current.contains(e.target) &&
          triggerRef.current && !triggerRef.current.contains(e.target)) {
        // Solo cerrar si no hay un picker/popover sub-flotante abierto
        if (!swatchOpenSlug && !deleteOpenSlug) closeDropdown()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open, swatchOpenSlug, deleteOpenSlug])

  // Escape
  useEffect(() => {
    if (!open) return
    function handler(e) {
      if (e.key === 'Escape') {
        // Si hay un sub-panel abierto, lo cierra primero
        if (swatchOpenSlug) { setSwatchOpenSlug(null); return }
        if (deleteOpenSlug) { setDeleteOpenSlug(null); return }
        if (renamingSlug) { setRenamingSlug(null); setRenameError(null); return }
        closeDropdown()
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, swatchOpenSlug, deleteOpenSlug, renamingSlug])

  // Flechas — navegación
  function handleSearchKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      const items = panelRef.current?.querySelectorAll('[role="option"]')
      items?.[0]?.focus()
    }
  }

  // ─── Filtrado ───────────────────────────────────────────────────────────────

  const filtered = categories.filter(c =>
    !search.trim() || c.label.toLowerCase().includes(search.trim().toLowerCase())
  )
  const hasCreate = search.trim().length > 0

  // ─── Seleccionar categoría ──────────────────────────────────────────────────

  function handleSelect(cat) {
    onChange?.(cat.slug, cat)
    closeDropdown()
  }

  // ─── Crear categoría ────────────────────────────────────────────────────────

  async function handleCreate() {
    const label = search.trim()
    if (!label) return
    setCreatingLoading(true)
    setCreateError(null)
    try {
      const created = await api.createCategory({ label })
      setCategories(prev => [...prev, created])
      onChange?.(created.slug, created)
      showToast(`Categoría «${created.label}» creada`)
      closeDropdown()
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setCreateError('Ya existe una categoría con ese nombre')
      } else {
        showToast('No se pudo completar la acción')
        setCreateError(e instanceof ApiError ? e.detail : 'Error de red')
      }
    } finally {
      setCreatingLoading(false)
    }
  }

  // ─── Renombrar ──────────────────────────────────────────────────────────────

  function startRename(cat) {
    setRenamingSlug(cat.slug)
    setRenameValue(cat.label)
    setRenameError(null)
    setSwatchOpenSlug(null)
    setDeleteOpenSlug(null)
  }

  async function confirmRename() {
    const label = renameValue.trim()
    if (!label) { setRenameError('El nombre no puede estar vacío'); return }
    const cat = categories.find(c => c.slug === renamingSlug)
    if (label === cat?.label) { setRenamingSlug(null); return }
    setRenameLoading(true)
    setRenameError(null)
    try {
      const updated = await api.patchCategory(renamingSlug, { label })
      setCategories(prev => prev.map(c => c.slug === renamingSlug ? { ...c, label: updated.label } : c))
      showToast(`Categoría renombrada a «${updated.label}»`)
      setRenamingSlug(null)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setRenameError('Ya existe una categoría con este nombre')
      } else {
        setRenameError(e instanceof ApiError ? e.detail : 'Error de red')
      }
    } finally {
      setRenameLoading(false)
    }
  }

  // ─── Cambiar color ──────────────────────────────────────────────────────────

  async function handleColorSelect(slug, newColor) {
    setSwatchOpenSlug(null)
    // Optimistic update
    const prev = categories.find(c => c.slug === slug)?.color ?? null
    setCategories(cats => cats.map(c => c.slug === slug ? { ...c, color: newColor } : c))
    setSwatchLoading(slug)
    try {
      await api.patchCategory(slug, { color: newColor })
      showToast('Color actualizado')
    } catch {
      // Revertir
      setCategories(cats => cats.map(c => c.slug === slug ? { ...c, color: prev } : c))
      showToast('No se pudo completar la acción')
    } finally {
      setSwatchLoading(null)
    }
  }

  // ─── Borrar categoría ────────────────────────────────────────────────────────

  async function handleDeleteConfirm(slug) {
    setDeleteLoading(true)
    try {
      const res = await api.deleteCategory(slug)
      setCategories(prev => prev.filter(c => c.slug !== slug))
      const n = res?.reassigned_count ?? 0
      showToast(n > 0 ? `Categoría eliminada · ${n} rutas reasignadas` : 'Categoría eliminada')
      setDeleteOpenSlug(null)
      // Si era la seleccionada, limpiar selección
      if (value === slug) onChange?.(null, null)
    } catch (e) {
      showToast('No se pudo completar la acción')
    } finally {
      setDeleteLoading(false)
    }
  }

  // ─── Render: Trigger ────────────────────────────────────────────────────────

  const triggerContent = () => {
    if (loadingCats) {
      return (
        <span style={{
          display: 'inline-block',
          width: '80px', height: '14px',
          background: 'var(--surface-2)',
          borderRadius: 'var(--radius-sm)',
          animation: 'skeleton-pulse 1.4s ease-in-out infinite',
        }} />
      )
    }
    if (loadError) {
      return (
        <span style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '12px', color: 'var(--danger)' }}>
          <IconWarning size={13} /> Sin conexión
        </span>
      )
    }
    const cat = selectedCat
    return (
      <span style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: 1, minWidth: 0 }}>
        {/* Swatch */}
        <span style={{
          display: 'inline-block',
          width: '10px', height: '10px', minWidth: '10px',
          borderRadius: '50%',
          background: cat?.color ?? undefined,
          border: cat?.color ? 'none' : '1.5px dashed var(--border-strong)',
          flexShrink: 0,
          boxSizing: 'border-box',
        }} />
        <span style={{
          fontSize: '13px', color: 'var(--text)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {cat?.label ?? 'Sin categoría'}
        </span>
      </span>
    )
  }

  // ─── Render: Panel de lista ─────────────────────────────────────────────────

  const panelContent = (
    <div
      ref={panelRef}
      role="listbox"
      id={listboxId}
      aria-label="Categorías disponibles"
      style={{
        position: isMobile ? 'fixed' : 'absolute',
        ...(isMobile
          ? {
              insetInline: 0,
              bottom: 0,
              top: 'auto',
              borderRadius: 'var(--radius-lg) var(--radius-lg) 0 0',
              maxHeight: '70vh',
            }
          : {
              top: '100%',
              insetInlineStart: 0,
              minWidth: '240px',
              maxWidth: '320px',
              marginTop: '4px',
            }),
        background: 'var(--surface)',
        border: '1px solid var(--border-strong)',
        borderRadius: isMobile ? 'var(--radius-lg) var(--radius-lg) 0 0' : 'var(--radius-md)',
        boxShadow: 'var(--shadow-lg)',
        zIndex: 250,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        animation: 'cc-panel-in var(--dur-base) var(--ease)',
      }}
      onClick={e => e.stopPropagation()}
    >
      {/* Handle de arrastre en móvil */}
      {isMobile && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 6px' }}>
          <div style={{ width: '36px', height: '4px', borderRadius: '2px', background: 'var(--border-strong)' }} />
        </div>
      )}

      {/* Campo de búsqueda */}
      <div style={{
        padding: '8px 10px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: '6px',
      }}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round"
          strokeLinejoin="round" aria-hidden="true" style={{ color: 'var(--text-tertiary)', flexShrink: 0 }}>
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          ref={searchInputRef}
          type="text"
          role="searchbox"
          aria-label="Buscar categoría"
          aria-autocomplete="list"
          aria-controls={listboxId}
          value={search}
          onChange={e => { setSearch(e.target.value); setCreateError(null) }}
          onKeyDown={e => {
            handleSearchKeyDown(e)
            if (e.key === 'Enter' && filtered.length === 0 && hasCreate) {
              e.preventDefault()
              handleCreate()
            }
          }}
          placeholder="Buscar o crear..."
          style={{
            flex: 1, border: 'none', background: 'transparent',
            fontSize: isMobile ? '16px' : '13px',
            color: 'var(--text)', fontFamily: 'inherit',
            outline: 'none',
          }}
        />
        {search && (
          <button
            type="button"
            aria-label="Limpiar búsqueda"
            onClick={() => { setSearch(''); setCreateError(null); searchInputRef.current?.focus() }}
            style={{
              border: 'none', background: 'transparent', cursor: 'pointer',
              color: 'var(--text-tertiary)', padding: 0, display: 'flex',
            }}
          >
            <IconX size={10} />
          </button>
        )}
      </div>

      {/* Lista de items */}
      <div style={{ overflowY: 'auto', maxHeight: isMobile ? 'calc(70vh - 120px)' : '204px' }}>
        {filtered.length === 0 && !hasCreate && (
          <div style={{ padding: '12px 10px', fontSize: '12px', color: 'var(--text-tertiary)', textAlign: 'center' }}>
            Sin categorías disponibles
          </div>
        )}
        {filtered.length === 0 && hasCreate && (
          <div style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-tertiary)', textAlign: 'center' }}>
            Sin resultados
          </div>
        )}
        {filtered.map(cat => (
          <CategoryItem
            key={cat.slug}
            cat={cat}
            isSelected={cat.slug === value}
            onSelect={handleSelect}
            onRenameStart={() => startRename(cat)}
            isRenaming={renamingSlug === cat.slug}
            renameValue={renameValue}
            renameError={renamingSlug === cat.slug ? renameError : null}
            onRenameChange={v => { setRenameValue(v); setRenameError(null) }}
            onRenameConfirm={confirmRename}
            onRenameCancel={() => { setRenamingSlug(null); setRenameError(null) }}
            renameLoading={renameLoading && renamingSlug === cat.slug}
            showSwatchPicker={swatchOpenSlug === cat.slug}
            onSwatchOpen={() => { setSwatchOpenSlug(cat.slug); setDeleteOpenSlug(null) }}
            onSwatchClose={() => setSwatchOpenSlug(null)}
            onSwatchSelect={color => handleColorSelect(cat.slug, color)}
            swatchLoading={swatchLoading === cat.slug}
            showDeletePop={deleteOpenSlug === cat.slug}
            onDeleteOpen={() => { setDeleteOpenSlug(cat.slug); setSwatchOpenSlug(null) }}
            onDeleteClose={() => setDeleteOpenSlug(null)}
            onDeleteConfirm={() => handleDeleteConfirm(cat.slug)}
            deleteLoading={deleteLoading && deleteOpenSlug === cat.slug}
            deletePopTriggerRef={el => { deletePopTriggerRefs.current[cat.slug] = el }}
            isMobile={isMobile}
          />
        ))}
      </div>

      {/* Pie: opción crear + botón "Nueva categoría" */}
      <div style={{ borderTop: '1px solid var(--border)', padding: '6px 8px', flexShrink: 0 }}>
        {/* Opción "+ Crear «texto»" cuando hay búsqueda */}
        {hasCreate && (
          <>
            {createError && (
              <p role="alert" style={{ fontSize: '11px', color: 'var(--danger)', margin: '0 0 4px', padding: '0 2px' }}>
                ⚠ {createError}
              </p>
            )}
            <button
              type="button"
              role="option"
              aria-label={`Crear categoría «${search.trim()}»`}
              onClick={handleCreate}
              disabled={creatingLoading}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                width: '100%', padding: '6px 8px',
                border: 'none', background: 'transparent',
                cursor: creatingLoading ? 'not-allowed' : 'pointer',
                fontSize: '13px', fontFamily: 'inherit',
                color: 'var(--btn-primary-bg)',
                fontWeight: 500,
                borderRadius: 'var(--radius-sm)',
                opacity: creatingLoading ? 0.7 : 1,
              }}
            >
              {creatingLoading ? <Spinner size={11} /> : '+'}
              Crear «{search.trim()}»
            </button>
          </>
        )}
        {/* Siempre visible: "+ Nueva categoría" */}
        {!hasCreate && (
          <button
            type="button"
            onClick={() => { searchInputRef.current?.focus() }}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              width: '100%', padding: '6px 8px',
              border: 'none', background: 'transparent',
              cursor: 'pointer',
              fontSize: '13px', fontFamily: 'inherit',
              color: 'var(--text-secondary)',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            + Nueva categoría
          </button>
        )}
      </div>
    </div>
  )

  const canOpen = !readOnly && !loadingCats && !loadError

  return (
    <>
      {/* Animación del panel */}
      <style>{`
        @keyframes cc-panel-in {
          from { opacity: 0; transform: translateY(-4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes skeleton-pulse { 0%,100%{opacity:1} 50%{opacity:.45} }
        @media (prefers-reduced-motion: reduce) {
          .cc-panel { animation: none !important; }
        }
        .cc-action-btn:hover { background: var(--surface-2) !important; color: var(--text) !important; }
        .cc-action-btn-danger:hover { background: var(--surface-2) !important; color: var(--danger) !important; }
      `}</style>

      <div style={{ position: 'relative', display: 'inline-block' }}>
        {/* ── Trigger ─────────────────────────────────── */}
        <button
          ref={triggerRef}
          type="button"
          role="combobox"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={open ? listboxId : undefined}
          aria-label={`Categoría: ${selectedCat?.label ?? 'Sin categoría'}`}
          disabled={loadingCats || !!loadError}
          onClick={canOpen ? (open ? closeDropdown : openDropdown) : (loadError ? loadCategories : undefined)}
          onKeyDown={e => {
            if ((e.key === 'Enter' || e.key === ' ') && !open && canOpen) {
              e.preventDefault(); openDropdown()
            }
          }}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            height: isMobile ? '44px' : '32px',
            padding: '0 10px',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--surface)',
            cursor: (loadingCats || !!loadError) ? (loadError ? 'pointer' : 'wait') : 'pointer',
            minWidth: '140px',
            fontFamily: 'inherit',
            boxSizing: 'border-box',
          }}
        >
          {triggerContent()}
          {!loadingCats && !loadError && (
            <span style={{ color: 'var(--text-tertiary)', flexShrink: 0 }}>
              <IconChevron size={12} up={open} />
            </span>
          )}
        </button>

        {/* ── Panel flotante (desktop) o overlay (móvil) ── */}
        {open && !isMobile && panelContent}
      </div>

      {/* Bottom sheet en móvil */}
      {open && isMobile && (
        <>
          <div
            aria-hidden="true"
            onClick={closeDropdown}
            style={{
              position: 'fixed', inset: 0,
              background: 'rgba(0,0,0,0.4)',
              zIndex: 249,
            }}
          />
          {panelContent}
        </>
      )}
    </>
  )
}
