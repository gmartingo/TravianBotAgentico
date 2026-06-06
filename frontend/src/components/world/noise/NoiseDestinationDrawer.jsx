/**
 * NoiseDestinationDrawer — Drawer lateral de detalle de un destino de ruido.
 *
 * Secciones:
 *  1. Header: label + badges + cerrar
 *  2. Editar destino (label, peso, is_safe — url_pattern y category R/O)
 *  3. Wizard Nueva Ruta (NoisePathWizard) — PROTAGONISTA
 *  4. Rutas existentes (NoisePathList) — secundarias
 *
 * Props:
 *  - open              {boolean}
 *  - dest              {object|null}
 *  - worldId           {number}
 *  - onClose           {Function}
 *  - triggerRef        {React.Ref}
 *  - onDestUpdated     {Function(dest)}
 *  - origins           {object|null}   — datos EP-N12 precargados desde NoiseTab
 *  - loadingOrigins    {boolean}
 *  - originsError      {string|null}
 *  - onOriginsRefreshed {Function(origins)}
 *  - onRetryOrigins    {Function}
 *
 * Optimización de rendimiento (v3 — prerender progresivo):
 *  - El drawer se mantiene SIEMPRE MONTADO (nunca return null).
 *  - La visibilidad se controla con visibility+pointer-events+aria-hidden.
 *  - PRERENDER PROGRESIVO: al abrir, el shell (header + secciones vacías con
 *    skeletons) se pinta en el frame 0. El contenido pesado (wizard, path list,
 *    form fields) se monta en el frame siguiente vía startTransition, de modo
 *    que el panel aparece al instante y el contenido "rellena" un tick después.
 *  - Los orígenes (EP-N12) se reciben como props desde NoiseTab (una sola carga).
 *  - Animación reducida a 150ms (era 220ms) manteniendo la fluidez.
 *  - NoiseConfigPanel y NoiseDestinationsTable en NoiseTab tienen React.memo para
 *    no re-renderizar cuando solo cambia el estado del drawer.
 *
 * Patrón: FarmListDrawer (mismo shell: overlay + panel inset-inline-end:0 + focus trap + ESC)
 * Spec: docs/design/noise-catalog-ui.md §6 (Drawer), §7
 */
import { useState, useRef, useEffect, useCallback, memo } from 'react'
import { useI18n } from '../../../i18n/index.jsx'
import { api, ApiError } from '../../../api/client.js'
import { Spinner, showToast, useFocusTrap } from '../../ui/uiUtils.jsx'
import { NoiseCategoryBadge } from './NoiseDestinationsTable.jsx'
import { NoisePathWizard } from './NoisePathWizard.jsx'
import { NoisePathList } from './NoisePathList.jsx'

// ── InheritedStepsPanelDrawer ─────────────────────────────────────────────────
// Tabla de pasos heredados (cadena de orígenes) para el drawer en modo template.
// Llama EP-RT11 GET /route-templates/{id}/chain y renderiza raíz→hoja.
// El último clic (el propio de la plantilla actual) se resalta.

function InheritedStepsPanelDrawer({ templateId, originTemplateId }) {
  const [chain, setChain] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!templateId) return
    setLoading(true)
    setError(null)
    api.getRouteTemplateChain(templateId)
      .then(data => setChain(data))
      .catch(err => setError(err instanceof ApiError ? err.detail : 'Error al cargar la cadena de orígenes'))
      .finally(() => setLoading(false))
  }, [templateId])

  if (!originTemplateId) return null

  const thStyle = {
    fontSize: '10px', fontWeight: 600, letterSpacing: '.04em',
    textTransform: 'uppercase', color: 'var(--text-secondary)',
    padding: '4px 8px', borderBottom: '1px solid var(--border)',
    background: 'var(--surface)', textAlign: 'start',
  }

  return (
    <section style={{ marginBottom: '24px' }}>
      <p style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-tertiary)', marginBottom: '8px' }}>
        Pasos heredados (raíz → hoja)
      </p>

      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-tertiary)', fontSize: '12px' }}>
          <Spinner size={11} /> Cargando cadena…
        </div>
      )}

      {error && (
        <p role="alert" style={{ fontSize: '12px', color: 'var(--danger)', margin: 0 }}>{error}</p>
      )}

      {chain && !loading && (
        <div style={{
          border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
          overflow: 'hidden',
        }}>
          {/* Aviso si el origen fue eliminado */}
          {chain.steps?.length <= 1 && (
            <div style={{
              padding: '6px 10px', fontSize: '11px', color: 'var(--text-secondary)',
              background: 'var(--accent-subtle)',
              borderBottom: '1px solid var(--border)',
            }}>
              Origen eliminado — ejecutará desde cualquier punto.
            </div>
          )}
          {chain.steps?.length > 0 ? (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ ...thStyle, width: '22px', textAlign: 'center' }}>#</th>
                  <th style={thStyle}>Plantilla</th>
                  <th style={thStyle}>Selector</th>
                  <th style={thStyle}>URL esperada</th>
                </tr>
              </thead>
              <tbody>
                {chain.steps.map((step, idx) => {
                  const isOwn = idx === chain.steps.length - 1
                  return (
                    <tr key={idx} style={{ background: isOwn ? 'var(--accent-subtle)' : undefined }}>
                      <td style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-tertiary)', textAlign: 'center' }}>
                        {idx + 1}
                      </td>
                      <td style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)', fontSize: '11px' }}>
                        <span style={{ fontWeight: isOwn ? 600 : 400, color: isOwn ? 'var(--accent-text)' : 'var(--text)' }}>
                          {step.label}
                        </span>
                        {isOwn && (
                          <span style={{ fontSize: '10px', color: 'var(--accent-text)', marginInlineStart: '4px', fontWeight: 600 }}>← este</span>
                        )}
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-tertiary)' }}>
                          {step.template_slug}
                        </div>
                      </td>
                      <td style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)' }}>
                        <code style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text)' }}>
                          {step.step?.selector ?? step.selector ?? '—'}
                        </code>
                      </td>
                      <td style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)' }}>
                        <code style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-tertiary)' }}>
                          {step.expected_url ?? step.step?.expected_url_after_click ?? '—'}
                        </code>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <p style={{ padding: '8px 10px', fontSize: '11px', color: 'var(--text-tertiary)', margin: 0 }}>
              La cadena no tiene pasos definidos.
            </p>
          )}
        </div>
      )}
    </section>
  )
}

function IconClose({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

// ── Skeleton de sección pesada ────────────────────────────────────────────────
// Se muestra en el frame 0 (antes de que el contenido pesado se monte).
// Coherente con el patrón skeleton/Spinner del proyecto (ver NoiseTab SkeletonTab).
const SectionSkeleton = memo(function SectionSkeleton({ rows = 3 }) {
  const pulse = {
    background: 'var(--surface-2)',
    borderRadius: 'var(--radius-sm)',
    animation: 'skeleton-pulse 1.4s ease-in-out infinite',
  }
  return (
    <>
      <style>{`@keyframes skeleton-pulse{0%,100%{opacity:1}50%{opacity:.45}}`}</style>
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          style={{ ...pulse, height: '32px', marginBottom: '8px', opacity: 1 - i * 0.15 }}
        />
      ))}
    </>
  )
})

export function NoiseDestinationDrawer({
  open, dest, worldId, onClose, triggerRef, onDestUpdated,
  origins, loadingOrigins, originsError, onOriginsRefreshed, onRetryOrigins,
  // Modo plantilla (Portal /rutas):
  //   mode="template" — dest es una RouteTemplate; los paths se cargan via EP-RT06.
  //   templateId     — id de la plantilla (usado para cargar paths en modo template).
  //   onTemplateSaved — callback(updatedTemplate) cuando se guarda en modo template.
  //   onTemplateDeleted — callback() cuando se borra en modo template.
  mode = 'world',
  templateId,
  onTemplateSaved,
  onTemplateDeleted,
}) {
  const { t } = useI18n()
  const panelRef = useRef(null)

  // (El skeleton de rutas se muestra con loadingPaths directamente —
  // ver la sección "Rutas existentes" más abajo. No se necesita estado extra aquí.)

  useFocusTrap(panelRef, open)

  // Enfocar primer campo al abrir
  useEffect(() => {
    if (open) {
      // Diferir ligeramente para que la animación CSS ya haya comenzado
      // y el elemento sea visible antes de recibir el foco.
      setTimeout(() => {
        panelRef.current?.querySelector('input, button')?.focus()
      }, 60)
    }
  }, [open])

  // Cerrar con ESC
  useEffect(() => {
    function handler(e) {
      if (e.key === 'Escape' && open) {
        onClose()
        triggerRef?.current?.focus()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose, triggerRef])

  // Campos editables del destino
  const [label, setLabel] = useState(dest?.label ?? '')
  const [weight, setWeight] = useState(dest?.navigation_weight ?? 1.0)
  const [isSafe, setIsSafe] = useState(dest?.is_safe ?? true)
  const [category, setCategory] = useState(dest?.category ?? '')
  const [saving, setSaving] = useState(false)
  const [destApiError, setDestApiError] = useState(null)

  // Paths state
  const [paths, setPaths] = useState([])
  const [loadingPaths, setLoadingPaths] = useState(false)
  const [pathsError, setPathsError] = useState(null)

  // Guardar el id del destino que tiene los paths cargados, para no recargar
  // cuando el drawer se cierra y reabre con el mismo destino.
  const loadedDestId = useRef(null)

  // Sync form con dest cuando cambia
  useEffect(() => {
    if (dest) {
      setLabel(dest.label ?? '')
      setWeight(dest.navigation_weight ?? 1.0)
      setIsSafe(dest.is_safe ?? true)
      setCategory(dest.category ?? '')
      setDestApiError(null)
    }
  }, [dest?.id])

  // Cargar paths: solo cuando abre y el destino cambia (no en cada re-apertura
  // del mismo destino si ya están cargados).
  // En mode="template" usa EP-RT06; en mode="world" usa EP-N07.
  const loadPaths = useCallback(async () => {
    if (!dest) return
    setLoadingPaths(true)
    setPathsError(null)
    try {
      let data
      if (mode === 'template') {
        const tid = templateId ?? dest.id
        data = await api.getRouteTemplatePaths(tid)
      } else {
        data = await api.getNoisePaths(worldId, dest.id)
      }
      setPaths(data?.paths ?? data ?? [])
      loadedDestId.current = dest.id
    } catch (e) {
      setPathsError(e instanceof ApiError ? e.detail : t('noise.paths.error'))
    } finally {
      setLoadingPaths(false)
    }
  }, [worldId, dest?.id, mode, templateId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (open && dest) {
      // Solo recargar si cambió el destino
      if (loadedDestId.current !== dest.id) {
        loadPaths()
      }
    }
    // Si se cierra, no limpiar paths: así están listos para la próxima apertura
    // del mismo destino sin espera.
  }, [open, dest?.id, loadPaths])

  async function handleSaveDest() {
    setSaving(true)
    setDestApiError(null)
    try {
      let updated
      if (mode === 'template') {
        // NOTA v2 rev.2: no pasar navigation_weight al PATCH de plantilla —
        // el peso vive en NoiseDestination por-mundo, no en la plantilla global.
        // category ahora es editable en mode="template".
        const tid = templateId ?? dest.id
        const categoryTrimmed = category.trim()
        updated = await api.updateRouteTemplate(tid, {
          label: label.trim() || undefined,
          is_safe: isSafe,
          ...(categoryTrimmed && categoryTrimmed !== dest.category ? { category: categoryTrimmed } : {}),
        })
        showToast(t('noise.drawer.saved'))
        onTemplateSaved?.(updated)
      } else {
        updated = await api.updateNoiseDestination(worldId, dest.id, {
          label: label.trim() || undefined,
          navigation_weight: weight,
          is_safe: isSafe,
        })
        showToast(t('noise.drawer.saved'))
        onDestUpdated?.(updated)
      }
    } catch (e) {
      setDestApiError(e instanceof ApiError ? e.detail : t('noise.drawer.saving'))
    } finally {
      setSaving(false)
    }
  }

  // useCallback estabiliza estos handlers para que React.memo en PathCard funcione:
  // si path/paths no cambian y estos callbacks son los mismos, PathCard no re-renderiza.
  const handlePathCreated = useCallback((path) => {
    setPaths(prev => [path, ...prev])
  }, [])

  const handlePathUpdated = useCallback((updated) => {
    setPaths(prev => prev.map(p => p.id === updated.id ? updated : p))
  }, [])

  const handlePathDeleted = useCallback((id) => {
    setPaths(prev => prev.filter(p => p.id !== id))
  }, [])

  // En modo template el peso no forma parte del formulario (v2 rev.2): label + category + is_safe.
  const isDirty = dest && (
    label !== (dest.label ?? '') ||
    (mode !== 'template' && weight !== (dest.navigation_weight ?? 1.0)) ||
    isSafe !== (dest.is_safe ?? true) ||
    (mode === 'template' && category.trim() !== (dest.category ?? ''))
  )

  // El drawer siempre está montado en el DOM.
  // Cuando está cerrado se oculta con visibility+pointer-events (no con return null)
  // para evitar el desmontaje/remontaje del subárbol en cada apertura.
  // aria-hidden="true" cuando está cerrado para que lectores de pantalla no
  // perciban el contenido oculto.

  return (
    <>
      {/* Overlay semitransparente — solo visible cuando open */}
      <div
        aria-hidden="true"
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,0.4)',
          zIndex: 300,
          // Mostrar/ocultar con opacity + pointer-events para no desmontar
          opacity: open ? 1 : 0,
          pointerEvents: open ? 'auto' : 'none',
          transition: 'opacity 150ms ease',
        }}
      />

      {/* Panel lateral */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-hidden={!open}
        aria-labelledby="noise-drawer-title"
        style={{
          position: 'fixed',
          insetBlock: 0,
          insetInlineEnd: 0,
          width: 'min(440px, 100vw)',
          background: 'var(--surface)',
          borderInlineStart: '1px solid var(--border)',
          boxShadow: 'var(--shadow-lg)',
          zIndex: 400,
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
          // Slide in/out: 100ms (era 150ms) — reduce el tiempo que el usuario espera
          // antes de ver el contenido. will-change: transform promueve a la GPU
          // para que la animación no cause recalcs de estilo en el main thread.
          transform: open ? 'translateX(0)' : 'translateX(100%)',
          opacity: open ? 1 : 0,
          transition: 'transform 100ms ease-out, opacity 100ms ease-out',
          willChange: 'transform',
          // Quitar de la interacción cuando está cerrado
          pointerEvents: open ? 'auto' : 'none',
          visibility: open ? 'visible' : 'hidden',
        }}
      >
        <style>{`
          @media (prefers-reduced-motion: reduce) {
            [role="dialog"][aria-hidden="true"],
            [role="dialog"][aria-hidden="false"] {
              transition: none !important;
            }
          }
        `}</style>

        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: '10px',
          padding: '14px 16px 12px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2
              id="noise-drawer-title"
              style={{ fontSize: '15px', fontWeight: 600, margin: 0, marginBottom: '4px' }}
            >
              {dest?.label || dest?.url_pattern || '…'}
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
              <code style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-tertiary)' }}>
                {dest?.url_pattern}
              </code>
              {dest?.category && <NoiseCategoryBadge category={dest.category} />}
              <span style={{
                fontSize: '11px',
                color: dest?.is_safe ? 'var(--success)' : 'var(--text-tertiary)',
              }}>
                {dest?.is_safe ? `✓ ${t('noise.destinations.safe')}` : `✗ ${t('noise.destinations.unsafe')}`}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => { onClose(); triggerRef?.current?.focus() }}
            aria-label={t('noise.drawer.close')}
            style={{
              width: '32px', height: '32px',
              border: 'none', background: 'transparent',
              cursor: 'pointer', flexShrink: 0,
              color: 'var(--text-secondary)',
              borderRadius: 'var(--radius-sm)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <IconClose size={16} />
          </button>
        </div>

        {/* Contenido */}
        <div style={{ flex: 1, padding: '16px', overflowY: 'auto' }}>

          {/* Sección: Editar destino — contenido inmediato (dest ya disponible al abrir) */}
          <section style={{ marginBottom: '24px' }}>
            <p style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-tertiary)', marginBottom: '10px' }}>
              {t('noise.drawer.editTitle')}
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {/* Label */}
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', fontWeight: 500 }}>
                  {t('noise.form.label')}
                </label>
                <input
                  type="text"
                  value={label}
                  onChange={e => setLabel(e.target.value)}
                  disabled={saving}
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

              {/* Peso de navegación (navigation_weight) — oculto en modo template (v2 rev.2) */}
              {/* En modo template el peso NO pertenece a la plantilla; se fija al clonar a un mundo. */}
              {mode !== 'template' && (
                <div>
                  <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', fontWeight: 500 }}>
                    {t('noise.drawer.weight')}
                    <span style={{ fontWeight: 400, color: 'var(--text-tertiary)', marginInlineStart: '6px' }}>
                      0.1 – 5.0
                    </span>
                  </label>
                  <input
                    type="number"
                    min="0.1"
                    max="5"
                    step="0.1"
                    value={weight}
                    onChange={e => {
                      const v = parseFloat(e.target.value)
                      // Clampar al rango válido [0.1, 5.0] (RN-FW06, CA-FW18)
                      if (!isNaN(v)) setWeight(Math.min(5.0, Math.max(0.1, v)))
                      else setWeight(1.0)
                    }}
                    disabled={saving}
                    aria-label={t('noise.drawer.weight')}
                    style={{
                      width: '80px', padding: '6px 8px',
                      border: '1px solid var(--border-strong)',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--surface)', color: 'var(--text)',
                      fontFamily: 'var(--font-mono)', fontSize: '13px',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  />
                </div>
              )}

              {/* is_safe */}
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '13px' }}>
                <input
                  type="checkbox"
                  checked={isSafe}
                  onChange={e => setIsSafe(e.target.checked)}
                  disabled={saving}
                  style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                />
                {t('noise.drawer.safe')}
              </label>

              {/* URL (R/O) */}
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>
                  {t('noise.drawer.urlReadOnly')}
                </label>
                <code style={{
                  display: 'block',
                  fontFamily: 'var(--font-mono)', fontSize: '12px',
                  color: 'var(--text-secondary)',
                  background: 'var(--surface-2)',
                  padding: '5px 8px',
                  borderRadius: 'var(--radius-sm)',
                }}>
                  {dest?.url_pattern}
                </code>
              </div>

              {/* Categoría — editable en mode="template", read-only en mode="world" */}
              {mode === 'template' ? (
                <div>
                  <label
                    htmlFor="drawer-category"
                    style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', fontWeight: 500 }}
                  >
                    Categoría
                  </label>
                  <input
                    id="drawer-category"
                    type="text"
                    list="drawer-category-datalist"
                    value={category}
                    onChange={e => setCategory(e.target.value)}
                    disabled={saving}
                    maxLength={50}
                    autoComplete="off"
                    placeholder="MAP, Estadísticas, Top 10…"
                    style={{
                      width: '100%',
                      padding: '6px 10px',
                      border: '1px solid var(--border-strong)',
                      borderRadius: 'var(--radius-sm)',
                      background: saving ? 'var(--surface-2)' : 'var(--surface)',
                      color: 'var(--text)',
                      fontFamily: 'inherit', fontSize: '13px',
                      boxSizing: 'border-box',
                    }}
                  />
                  <datalist id="drawer-category-datalist">
                    {['MAP','OASIS_INFO','PLAYER_PROFILE','MESSAGES','REPORTS','BUILDING_VIEW','OTHER','Estadísticas','Top 10'].map(c => (
                      <option key={c} value={c} />
                    ))}
                  </datalist>
                </div>
              ) : (
                <div>
                  <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>
                    {t('noise.drawer.categoryReadOnly')}
                  </label>
                  {dest?.category && <NoiseCategoryBadge category={dest.category} />}
                </div>
              )}

              {destApiError && (
                <p role="alert" style={{ fontSize: '12px', color: 'var(--danger)' }}>{destApiError}</p>
              )}

              {isDirty && (
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    onClick={handleSaveDest}
                    disabled={saving}
                    style={{
                      height: '32px', padding: '0 14px',
                      border: 'none',
                      background: saving ? 'var(--surface-2)' : 'var(--btn-primary-bg)',
                      color: saving ? 'var(--text-disabled)' : 'var(--btn-primary-text)',
                      borderRadius: 'var(--radius-sm)',
                      fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
                      cursor: saving ? 'not-allowed' : 'pointer',
                      display: 'flex', alignItems: 'center', gap: '6px',
                    }}
                  >
                    {saving && <Spinner size={12} />}
                    {saving ? t('noise.drawer.saving') : t('noise.drawer.saveChanges')}
                  </button>
                </div>
              )}
            </div>
          </section>

          <div style={{ height: '1px', background: 'var(--border)', marginBottom: '24px' }} />

          {/* Sección: Pasos heredados (cadena de orígenes) — solo en modo template con origen */}
          {mode === 'template' && dest?.origin_template_id != null && (
            <InheritedStepsPanelDrawer
              templateId={templateId ?? dest.id}
              originTemplateId={dest.origin_template_id}
            />
          )}
          {mode === 'template' && dest?.origin_template_id == null && (
            <div style={{
              fontSize: '12px', color: 'var(--text-tertiary)',
              padding: '8px', background: 'var(--surface-2)',
              borderRadius: 'var(--radius-sm)', marginBottom: '24px',
              lineHeight: 1.5,
            }}>
              Origen libre — el primer clic de esta ruta es visible desde cualquier página de Travian.
              Para encadenar esta ruta con otra, edita el origen en el catálogo.
            </div>
          )}

          {/* Sección: Wizard Nueva Ruta — contenido inmediato (origins precargados) */}
          <section style={{ marginBottom: '24px' }}>
            {dest && (
              <NoisePathWizard
                worldId={worldId}
                destId={dest.id}
                onCreated={handlePathCreated}
                origins={origins}
                loadingOrigins={loadingOrigins}
                originsError={originsError}
                onOriginsRefreshed={onOriginsRefreshed}
                onRetryOrigins={onRetryOrigins}
              />
            )}
          </section>

          <div style={{ height: '1px', background: 'var(--border)', marginBottom: '24px' }} />

          {/* Sección: Rutas existentes
              — skeleton mientras loadingPaths (primera carga por destino)
              — contenido inmediato en aperturas posteriores del mismo destino  */}
          <section>
            <p style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-tertiary)', marginBottom: '10px' }}>
              {t('noise.paths.title')} ({paths.length})
            </p>
            {loadingPaths ? (
              <SectionSkeleton rows={2} />
            ) : (
              <NoisePathList
                worldId={worldId}
                paths={paths}
                loading={false}
                error={pathsError}
                onRetry={loadPaths}
                onUpdate={handlePathUpdated}
                onDelete={handlePathDeleted}
              />
            )}
          </section>
        </div>
      </div>
    </>
  )
}
