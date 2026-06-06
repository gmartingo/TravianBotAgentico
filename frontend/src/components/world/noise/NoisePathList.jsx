/**
 * NoisePathList — Lista de rutas existentes en el drawer de destino.
 *
 * Muestra tarjetas colapsables para cada ruta:
 *  - Estado activa / inactiva / muerta (is_dead)
 *  - Icono ✎ en hover para renombrar el label inline (v4)
 *  - Botón "Editar pasos" visible en la cabecera (v4)
 *  - Botón ⋯ overflow menu que contiene "Eliminar ruta" (reemplaza el ✕ directo, v4)
 *  - Botón Reactivar cuando is_dead=true (EP-N09 con is_active=true)
 *  - Botón "Probar" (EP-N14) con estados idle/loading/result-ok/result-error/409/5xx
 *  - PathTestResultPanel expandible inline bajo la cabecera
 *  - Resumen de pasos en modo lectura cuando expandida
 *  - Editor avanzado (NoiseStepEditor) para editar pasos
 *  - DeletePopover para eliminar la ruta (desde el menú ⋯)
 *
 * Props:
 *  - worldId  {number}
 *  - paths    {Array}
 *  - loading  {boolean}
 *  - error    {string|null}
 *  - onRetry  {Function}
 *  - onUpdate {Function(updatedPath)} — cuando la ruta se actualiza
 *  - onDelete {Function(pathId)}      — cuando la ruta se elimina
 *
 * Spec: docs/design/noise-catalog-ui.md §6c (v4), §7, §8 delta v4, §10, §12, §13 v4
 */
import { useState, useRef, useEffect, useCallback, memo } from 'react'
import { useI18n } from '../../../i18n/index.jsx'
import { api, ApiError } from '../../../api/client.js'
import { Spinner, showToast } from '../../ui/uiUtils.jsx'
import { DeletePopover } from '../../ui/DeletePopover.jsx'
import { NoiseStepEditor } from './NoiseStepEditor.jsx'
import { PathTestResultPanel } from './PathTestResultPanel.jsx'

// ── Icono SVG pencil (12px) ─────────────────────────────────────────────────
function IconPencil() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  )
}

// ── Icono SVG warning (13px) ────────────────────────────────────────────────
function IconWarning({ size = 12 }) {
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

// ── Badge origen de ruta ────────────────────────────────────────────────────
function NoiseOriginBadge({ origin }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      borderRadius: 'var(--radius-full)',
      padding: '1px 7px',
      fontSize: '11px', fontWeight: 500,
      background: 'var(--surface-2)',
      color: 'var(--text-secondary)',
      whiteSpace: 'nowrap', fontFamily: 'var(--font-mono)',
    }}>
      {origin?.startsWith('VILLAGE_') ? origin.replace('VILLAGE_', 'V') : origin}
    </span>
  )
}

// ── PathCard ─────────────────────────────────────────────────────────────────
// React.memo: evita re-render de todas las cards cuando `paths` array no cambia.
// onUpdate/onDelete vienen de handlePathUpdated/handlePathDeleted en el drawer,
// que son funciones inline — son estables en referencia (no usan useCallback),
// pero al ser pasadas por el drawer que no re-renderiza cuando contentReady cambia
// (el drawer re-renderiza pero paths/callbacks no cambian), el memo tiene efecto.
const PathCard = memo(function PathCard({ path, worldId, onUpdate, onDelete }) {
  const { t } = useI18n()

  // ── Estado expand/editor ──────────────────────────────────────────────────
  const [expanded, setExpanded] = useState(false)
  const [editingSteps, setEditingSteps] = useState(false)
  const [reactivating, setReactivating] = useState(false)
  const [savingSteps, setSavingSteps] = useState(false)
  const [stepsError, setStepsError] = useState(null)

  // ── Estado renombrado inline (v4) ─────────────────────────────────────────
  const [renamingLabel, setRenamingLabel] = useState(false)
  const [renameValue, setRenameValue] = useState(path.label)
  const [renameSaving, setRenameSaving] = useState(false)
  const [renameError, setRenameError] = useState(null)

  // ── Estado overflow menu ⋯ (v4) ───────────────────────────────────────────
  const [overflowMenuOpen, setOverflowMenuOpen] = useState(false)
  const [deletePopoverOpen, setDeletePopoverOpen] = useState(false)

  // ── Estado "Probar ruta" (EP-N14 v3) ─────────────────────────────────────
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [testDurationMs, setTestDurationMs] = useState(null)
  const [testError409, setTestError409] = useState(null)
  const [testError5xx, setTestError5xx] = useState(null)

  // ── Refs para foco ────────────────────────────────────────────────────────
  const liveRef = useRef(null)
  const testBtnRef = useRef(null)
  const renameBtnRef = useRef(null)   // ref al lápiz ✎, para devolver foco al cancelar
  const labelBtnRef = useRef(null)    // ref al label/botón expand, foco al confirmar
  const overflowBtnRef = useRef(null)
  const overflowMenuRef = useRef(null)
  const renameInputId = `rename-error-${path.id}`

  const isDead = path.is_dead === true
  const isActive = path.is_active !== false && !isDead

  // ── Cerrar overflow menu con ESC o click fuera ────────────────────────────
  useEffect(() => {
    if (!overflowMenuOpen) return
    function handleKey(e) {
      if (e.key === 'Escape') {
        setOverflowMenuOpen(false)
        overflowBtnRef.current?.focus()
      }
    }
    function handleClick(e) {
      if (
        overflowMenuRef.current && !overflowMenuRef.current.contains(e.target) &&
        overflowBtnRef.current && !overflowBtnRef.current.contains(e.target)
      ) {
        setOverflowMenuOpen(false)
      }
    }
    document.addEventListener('keydown', handleKey)
    document.addEventListener('mousedown', handleClick)
    return () => {
      document.removeEventListener('keydown', handleKey)
      document.removeEventListener('mousedown', handleClick)
    }
  }, [overflowMenuOpen])

  // ── Sincronizar renameValue si path.label cambia externamente ─────────────
  useEffect(() => {
    if (!renamingLabel) {
      setRenameValue(path.label)
    }
  }, [path.label, renamingLabel])

  // ── Handlers reactivar ────────────────────────────────────────────────────
  async function handleReactivate() {
    setReactivating(true)
    try {
      const updated = await api.updateNoisePath(worldId, path.id, { is_active: true })
      showToast(t('noise.paths.reactivated'))
      onUpdate(updated)
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('noise.paths.saveError'))
    } finally {
      setReactivating(false)
    }
  }

  // ── Handlers editor de pasos ──────────────────────────────────────────────
  async function handleSaveSteps(steps) {
    setSavingSteps(true)
    setStepsError(null)
    try {
      const updated = await api.updateNoisePath(worldId, path.id, { steps })
      showToast(t('noise.paths.saved'))
      onUpdate(updated)
      setEditingSteps(false)
    } catch (e) {
      setStepsError(e instanceof ApiError ? e.detail : t('noise.paths.saveError'))
    } finally {
      setSavingSteps(false)
    }
  }

  // ── Handlers eliminar ─────────────────────────────────────────────────────
  async function handleDeleteConfirm() {
    await api.deleteNoisePath(worldId, path.id)
    showToast(t('noise.paths.deleted'))
    onDelete(path.id)
    setDeletePopoverOpen(false)
  }

  // ── Handlers renombrado (v4) ──────────────────────────────────────────────
  function startRenaming() {
    setRenameValue(path.label)
    setRenameError(null)
    setRenamingLabel(true)
  }

  function handleRenameCancel() {
    setRenamingLabel(false)
    setRenameValue(path.label)
    setRenameError(null)
    // Devuelve foco al lápiz ✎ (trigger del modo edición)
    // pequeño timeout para que el DOM haya restaurado el botón antes del focus
    setTimeout(() => renameBtnRef.current?.focus(), 0)
  }

  async function handleRenameConfirm() {
    const trimmed = renameValue.trim()
    if (!trimmed) {
      setRenameError(t('noise.paths.renameEmptyError'))
      return
    }
    // Si el valor no ha cambiado, cancelar sin llamar a la API
    if (trimmed === path.label) {
      setRenamingLabel(false)
      setRenameError(null)
      setTimeout(() => labelBtnRef.current?.focus(), 0)
      return
    }
    setRenameSaving(true)
    setRenameError(null)
    try {
      const updated = await api.updateNoisePath(worldId, path.id, { label: trimmed })
      showToast(t('noise.paths.renamed'))
      onUpdate(updated)
      setRenamingLabel(false)
      // Devuelve foco al label/botón-expand de la tarjeta
      setTimeout(() => labelBtnRef.current?.focus(), 0)
    } catch (e) {
      const msg = e instanceof ApiError
        ? (e.detail ?? t('noise.paths.renameError'))
        : t('noise.paths.renameError')
      setRenameError(msg)
    } finally {
      setRenameSaving(false)
    }
  }

  function handleRenameKeyDown(e) {
    if (e.key === 'Enter') { e.preventDefault(); handleRenameConfirm() }
    if (e.key === 'Escape') { e.preventDefault(); handleRenameCancel() }
  }

  // ── Handler "Editar pasos" desde cabecera (v4) ─────────────────────────────
  function handleEditStepsFromHeader() {
    setExpanded(true)
    setEditingSteps(true)
  }

  // ── Handlers test (EP-N14 v3) ──────────────────────────────────────────────
  async function handleTest() {
    setTestResult(null)
    setTestError409(null)
    setTestError5xx(null)
    setTesting(true)
    const t0 = Date.now()
    try {
      const result = await api.testNoisePath(worldId, path.id)
      const duration = Date.now() - t0
      setTestDurationMs(duration)
      setTestResult(result)
      if (liveRef.current) {
        const msg = result.overall === 'ok'
          ? t('noise.test.resultOk')
          : t('noise.test.resultError').replace('{n}', result.aborted_at_step ?? '?')
        liveRef.current.textContent = msg
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setTestError409(e.detail ?? 'Error 409')
      } else {
        setTestError5xx(
          e instanceof ApiError ? (e.detail ?? t('noise.test.error5xx')) : t('noise.test.error5xx')
        )
      }
    } finally {
      setTesting(false)
    }
  }

  function handleCloseResult() {
    setTestResult(null)
    setTestDurationMs(null)
    if (testBtnRef.current) testBtnRef.current.focus()
  }

  // ── Estilos de botón secundario mini (reutilizado en varios botones) ───────
  const btnMiniStyle = {
    display: 'inline-flex', alignItems: 'center', gap: '4px',
    height: '24px', padding: '0 8px',
    border: '1px solid var(--border-strong)',
    background: 'var(--surface)', color: 'var(--text)',
    borderRadius: 'var(--radius-sm)',
    fontFamily: 'inherit', fontSize: '11px',
    cursor: 'pointer',
    flexShrink: 0,
  }

  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-sm)',
      overflow: 'hidden',
      marginBottom: '8px',
    }}>
      {/* Nodo aria-live oculto para anunciar resultados del test a lectores de pantalla */}
      <span
        ref={liveRef}
        aria-live="polite"
        aria-atomic="true"
        style={{
          position: 'absolute',
          width: '1px', height: '1px',
          overflow: 'hidden',
          clip: 'rect(0 0 0 0)',
          whiteSpace: 'nowrap',
        }}
      />

      {/* ── Cabecera (v4) ──────────────────────────────────────────────────── */}
      <div
        className="path-header"
        style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          padding: '8px 10px',
          background: isDead ? 'rgba(201,53,44,.04)' : 'var(--surface)',
          flexWrap: 'wrap',
          position: 'relative',
        }}
      >
        {/* Icono ⚠ solo en rutas muertas */}
        {isDead && (
          <span style={{ color: 'var(--danger)', flexShrink: 0 }}>
            <IconWarning size={13} />
          </span>
        )}

        {/* ── Label + lápiz ✎ ── */}
        {renamingLabel ? (
          /* ── Modo edición inline ── */
          <>
            <input
              type="text"
              value={renameValue}
              onChange={e => { setRenameValue(e.target.value); setRenameError(null) }}
              onKeyDown={handleRenameKeyDown}
              disabled={renameSaving}
              autoFocus
              aria-label={t('noise.paths.renameInput')}
              aria-describedby={renameError ? renameInputId : undefined}
              style={{
                flex: 1, padding: '4px 8px',
                border: `1px solid ${renameError ? 'var(--danger)' : 'var(--border-strong)'}`,
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)', color: 'var(--text)',
                fontFamily: 'inherit', fontSize: '13px',
                opacity: renameSaving ? 0.7 : 1,
                minWidth: '100px',
                outline: 'none',
              }}
              onFocus={e => { e.target.style.outline = '2px solid var(--accent)' }}
              onBlur={e => { e.target.style.outline = 'none' }}
            />
            {/* Botón confirmar ✓ */}
            <button
              type="button"
              onClick={handleRenameConfirm}
              disabled={renameSaving || !renameValue.trim()}
              aria-label={t('noise.paths.renameConfirm')}
              aria-disabled={renameSaving || !renameValue.trim() ? 'true' : undefined}
              style={{
                width: '22px', height: '22px',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                border: '1px solid var(--border-strong)',
                background: 'var(--surface)',
                borderRadius: 'var(--radius-sm)',
                cursor: (renameSaving || !renameValue.trim()) ? 'not-allowed' : 'pointer',
                opacity: (renameSaving || !renameValue.trim()) ? 0.5 : 1,
                flexShrink: 0,
                fontSize: '12px',
                color: 'var(--success)',
              }}
            >
              {renameSaving ? <Spinner size={10} /> : '✓'}
            </button>
            {/* Botón cancelar ✕ */}
            <button
              type="button"
              onClick={handleRenameCancel}
              disabled={renameSaving}
              aria-label={t('noise.paths.renameCancel')}
              style={{
                width: '22px', height: '22px',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                border: 'none', background: 'transparent',
                borderRadius: 'var(--radius-sm)',
                cursor: renameSaving ? 'not-allowed' : 'pointer',
                opacity: renameSaving ? 0.5 : 1,
                flexShrink: 0,
                fontSize: '12px',
                color: 'var(--text-tertiary)',
              }}
            >
              ✕
            </button>
          </>
        ) : (
          /* ── Modo normal: label (clicable para expand) + lápiz en hover ── */
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flex: 1, minWidth: 0 }}>
            <button
              ref={labelBtnRef}
              type="button"
              aria-expanded={expanded}
              aria-controls={`path-body-${path.id}`}
              onClick={() => setExpanded(v => !v)}
              style={{
                appearance: 'none', border: 'none', background: 'transparent',
                cursor: 'pointer', padding: 0, textAlign: 'start',
                fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
                color: isDead ? 'var(--text-secondary)' : 'var(--text)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}
            >
              {path.label}
            </button>
            {/* Icono lápiz ✎ — visible solo en hover de .path-header */}
            <button
              ref={renameBtnRef}
              type="button"
              onClick={e => { e.stopPropagation(); startRenaming() }}
              aria-label={t('noise.paths.renameBtn')}
              className="rename-pencil"
              style={{
                appearance: 'none', border: 'none', background: 'transparent',
                cursor: 'pointer', padding: '4px',
                color: 'var(--text-tertiary)',
                borderRadius: 'var(--radius-sm)',
                display: 'inline-flex', alignItems: 'center',
                flexShrink: 0,
                /* La visibilidad se controla por CSS: opacity:0 → 1 en hover */
                opacity: 0,
                transition: 'opacity 150ms',
              }}
            >
              <IconPencil />
            </button>
          </div>
        )}

        {/* Origin badge */}
        <NoiseOriginBadge origin={path.origin} />

        {/* Estado badge */}
        {isDead ? (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '4px',
            fontSize: '11px', fontWeight: 500,
            color: 'var(--danger)',
            background: 'rgba(201,53,44,.10)',
            borderRadius: 'var(--radius-full)',
            padding: '1px 7px',
            fontFamily: 'var(--font-mono)',
            whiteSpace: 'nowrap',
          }}>
            ○ {t('noise.paths.dead')}
            {path.consecutive_failures_count > 0 && (
              <> · {t('noise.paths.deadFails').replace('{n}', path.consecutive_failures_count)}</>
            )}
          </span>
        ) : isActive ? (
          <span style={{
            fontSize: '11px', fontWeight: 500,
            color: 'var(--success)',
            background: 'rgba(36,138,61,.10)',
            borderRadius: 'var(--radius-full)',
            padding: '1px 7px',
            whiteSpace: 'nowrap',
          }}>
            ● {t('noise.paths.active')}
          </span>
        ) : (
          <span style={{
            fontSize: '11px',
            color: 'var(--text-tertiary)',
            background: 'var(--surface-2)',
            borderRadius: 'var(--radius-full)',
            padding: '1px 7px',
            whiteSpace: 'nowrap',
          }}>
            {t('noise.paths.inactive')}
          </span>
        )}

        {/* Reactivar si dead */}
        {isDead && (
          <button
            type="button"
            onClick={handleReactivate}
            disabled={reactivating}
            style={{
              ...btnMiniStyle,
              cursor: reactivating ? 'not-allowed' : 'pointer',
              opacity: reactivating ? 0.7 : 1,
            }}
          >
            {reactivating && <Spinner size={10} />}
            {reactivating ? t('noise.paths.reactivating') : t('noise.paths.reactivate')}
          </button>
        )}

        {/* ── Botón "Probar" (EP-N14 v3) — SOLO en modo MUNDO. En el catálogo global de
             plantillas (worldId == null) se prueba con el botón "Probar" de la FILA, que
             abre el panel "Probar ruta" con selección de mundo (EP-RT10-v3). Aquí no hay
             mundo, así que se oculta para no llamar a /worlds/null/noise/paths/.../test ── */}
        {!renamingLabel && worldId != null && (
          <button
            ref={testBtnRef}
            type="button"
            onClick={handleTest}
            disabled={testing}
            aria-label={testing ? t('noise.test.testing') : t('noise.test.testBtn')}
            aria-busy={testing ? 'true' : undefined}
            aria-disabled={testing ? 'true' : undefined}
            style={{
              ...btnMiniStyle,
              cursor: testing ? 'not-allowed' : 'pointer',
              opacity: testing ? 0.7 : 1,
            }}
          >
            {testing && <Spinner size={10} />}
            {testing ? t('noise.test.testing') : t('noise.test.testBtn')}
          </button>
        )}

        {/* ── Botón "Editar pasos" en cabecera (NUEVO v4) — oculto durante renombrado ── */}
        {!renamingLabel && (
          <button
            type="button"
            onClick={handleEditStepsFromHeader}
            aria-controls={`path-body-${path.id}`}
            aria-expanded={expanded && editingSteps}
            style={{
              ...btnMiniStyle,
              cursor: 'pointer',
            }}
          >
            {t('noise.paths.editSteps')}
          </button>
        )}

        {/* Chevron expand/colapsar */}
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={`path-body-${path.id}`}
          onClick={() => setExpanded(v => !v)}
          style={{
            appearance: 'none', border: 'none', background: 'transparent',
            cursor: 'pointer', padding: '4px',
            fontSize: '10px', color: 'var(--text-tertiary)',
            transition: 'transform 200ms ease',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            flexShrink: 0,
          }}
          aria-label={expanded ? t('noise.paths.collapse') : t('noise.paths.expand')}
        >
          ▼
        </button>

        {/* ── Botón ⋯ overflow menu + DeletePopover (v4) ─────────────────── */}
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <button
            ref={overflowBtnRef}
            type="button"
            onClick={() => setOverflowMenuOpen(v => !v)}
            aria-label={t('noise.paths.moreActions')}
            aria-expanded={overflowMenuOpen}
            aria-haspopup="menu"
            style={{
              width: '26px', height: '26px',
              border: 'none', background: 'transparent',
              cursor: 'pointer',
              color: 'var(--text-tertiary)', fontSize: '14px',
              borderRadius: 'var(--radius-sm)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              letterSpacing: '1px',
            }}
          >
            ⋯
          </button>

          {/* Mini-popover menú de overflow */}
          {overflowMenuOpen && (
            <div
              ref={overflowMenuRef}
              role="menu"
              style={{
                position: 'absolute', top: '100%', insetInlineEnd: 0,
                background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)', boxShadow: 'var(--shadow-md)',
                minWidth: '160px', zIndex: 50, padding: '4px 0',
              }}
            >
              <button
                role="menuitem"
                type="button"
                onClick={() => {
                  setOverflowMenuOpen(false)
                  setDeletePopoverOpen(true)
                }}
                style={{
                  width: '100%', textAlign: 'start', padding: '8px 12px',
                  border: 'none', background: 'transparent',
                  color: 'var(--danger)', fontSize: '13px',
                  cursor: 'pointer', fontFamily: 'inherit',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'rgba(201,53,44,.08)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
              >
                {t('noise.paths.delete')}
              </button>
            </div>
          )}

          {/* DeletePopover — misma API que en v3 */}
          {deletePopoverOpen && (
            <DeletePopover
              question={t('noise.paths.deleteConfirm')
                .replace('{label}', path.label)
                .replace('{n}', path.steps?.length ?? 0)
              }
              confirmLabel="Eliminar"
              cancelLabel="Cancelar"
              onConfirm={handleDeleteConfirm}
              onCancel={() => {
                setDeletePopoverOpen(false)
                overflowBtnRef.current?.focus()
              }}
              triggerRef={{ current: null }}
            />
          )}
        </div>

        {/* ── Segunda línea: caption loading (test) ── */}
        {testing && (
          <span style={{
            fontSize: '11px',
            color: 'var(--text-tertiary)',
            width: '100%',
            paddingInlineStart: '8px',
          }}>
            {t('noise.test.loadingHint')}
          </span>
        )}

        {/* ── Segunda línea: aviso 409 inline (role="alert" para SR inmediato) ── */}
        {testError409 && (
          <div
            role="alert"
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              fontSize: '12px', color: 'var(--text-secondary)',
              width: '100%',
              paddingInlineStart: '8px',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round"
              aria-hidden="true" style={{ flexShrink: 0 }}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="8" strokeWidth="3" strokeLinecap="round" />
              <line x1="12" y1="12" x2="12" y2="16" />
            </svg>
            {testError409}
          </div>
        )}

        {/* ── Segunda línea: error 5xx ── */}
        {testError5xx && (
          <span style={{
            fontSize: '12px', color: 'var(--danger)',
            width: '100%',
            paddingInlineStart: '8px',
          }}>
            {testError5xx}
          </span>
        )}

        {/* ── Segunda línea: error de renombrado inline ── */}
        {renameError && (
          <span
            id={renameInputId}
            role="alert"
            style={{
              width: '100%', paddingInlineStart: '4px',
              fontSize: '11px', color: 'var(--danger)',
            }}
          >
            {renameError}
          </span>
        )}
      </div>

      {/* ── PathTestResultPanel — inline entre cabecera y cuerpo expandido ── */}
      {testResult && (
        <PathTestResultPanel
          result={testResult}
          pathSteps={path.steps}
          durationMs={testDurationMs}
          onClose={handleCloseResult}
        />
      )}

      {/* ── Cuerpo expandido ─────────────────────────────────────────────── */}
      {expanded && (
        <div
          id={`path-body-${path.id}`}
          style={{
            borderTop: '1px solid var(--border)',
            padding: '10px 12px',
            background: 'var(--surface-2)',
          }}
        >
          {isDead && (
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '10px' }}>
              {t('noise.paths.reactivateHint')}
            </p>
          )}

          {editingSteps ? (
            <NoiseStepEditor
              initialSteps={path.steps ?? []}
              saving={savingSteps}
              apiError={stepsError}
              onSave={handleSaveSteps}
              onCancel={() => { setEditingSteps(false); setStepsError(null) }}
            />
          ) : (
            <>
              {/* Resumen pasos R/O */}
              {(path.steps ?? []).length === 0 ? (
                <p style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>Sin pasos.</p>
              ) : (
                <div style={{ marginBottom: '10px' }}>
                  {path.steps.map((step, i) => (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'center', gap: '8px',
                      fontSize: '12px', color: 'var(--text-secondary)',
                      padding: '3px 0',
                      borderBottom: i < path.steps.length - 1 ? '1px solid var(--border)' : undefined,
                    }}>
                      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', minWidth: '16px' }}>{i}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', background: 'var(--surface)', padding: '1px 5px', borderRadius: 'var(--radius-full)' }}>
                        {step.action}
                      </span>
                      <code style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', flex: 1, wordBreak: 'break-all' }}>
                        {step.selector}
                      </code>
                      {step.expected_url_after_click && (
                        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
                          → {step.expected_url_after_click}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {/* "Editar pasos" también en el cuerpo expandido (mantener para consistencia visual) */}
              <button
                type="button"
                onClick={() => setEditingSteps(true)}
                style={{
                  height: '28px', padding: '0 10px',
                  border: '1px solid var(--border-strong)',
                  background: 'var(--surface)', color: 'var(--text-secondary)',
                  borderRadius: 'var(--radius-sm)',
                  fontFamily: 'inherit', fontSize: '12px',
                  cursor: 'pointer',
                }}
              >
                {t('noise.paths.editSteps')}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
})

// ── NoisePathList ─────────────────────────────────────────────────────────────
export function NoisePathList({ worldId, paths, loading, error, onRetry, onUpdate, onDelete }) {
  const { t } = useI18n()

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-tertiary)', fontSize: '13px', padding: '12px 0' }}>
        <Spinner size={13} /> {t('noise.paths.loading')}
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ fontSize: '13px', color: 'var(--danger)', padding: '8px 0' }}>
        {error}
        <button
          type="button"
          onClick={onRetry}
          style={{
            marginInlineStart: '8px',
            appearance: 'none', border: 'none', background: 'transparent',
            color: 'var(--accent-text)', cursor: 'pointer',
            fontFamily: 'inherit', fontSize: '13px', textDecoration: 'underline',
          }}
        >
          {t('noise.paths.retry')}
        </button>
      </div>
    )
  }

  if ((paths ?? []).length === 0) {
    return (
      <p style={{ fontSize: '12px', color: 'var(--text-tertiary)', fontStyle: 'italic' }}>
        {t('noise.paths.empty')}
      </p>
    )
  }

  return (
    <div>
      {paths.map(path => (
        <PathCard
          key={path.id}
          path={path}
          worldId={worldId}
          onUpdate={onUpdate}
          onDelete={onDelete}
        />
      ))}
    </div>
  )
}
