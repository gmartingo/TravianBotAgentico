/**
 * RouteTemplatesPage — Portal del desarrollador de rutas (/rutas).
 *
 * Implementa el mockup aprobado: frontend/mockups/rutas.playground.html
 * Spec funcional: docs/specs/route-templates-developer-portal.md
 *
 * Bloques implementados:
 *  A — Cabecera (título + descripción + "Nueva plantilla")
 *  B — Barra de filtros (búsqueda texto + selector de categoría)
 *  C — Tabla de plantillas (con datos)
 *  D — Estado vacío (sin plantillas)
 *  E — Drawer de edición (reutiliza NoiseDestinationDrawer mode="template")
 *  F — Modal "Clonar a mundo"
 *  G — Panel resultado del test (reutiliza PathTestResultPanel)
 *  H — Panel re-sync (mundos con la plantilla, botón Sincronizar)
 *  I — Banner seed inicial (se muestra solo la primera vez)
 *
 * Estado cargando: skeleton table.
 * Estado error: banner de error con reintentar.
 * Todos los estados de CA-RT23.
 *
 * Responsive (DESIGN.md §17):
 *  - Columnas P2 (Pasos, Peso, Estado) ocultas en móvil < 768px.
 *  - Targets ≥ 44px en móvil.
 *  - Barra de filtros colapsa en stack.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useI18n } from '../i18n/index.jsx'
import { api, ApiError } from '../api/client.js'
import { Spinner, showToast } from '../components/ui/uiUtils.jsx'
import { NoiseDestinationDrawer } from '../components/world/noise/NoiseDestinationDrawer.jsx'
import { PathTestResultPanel } from '../components/world/noise/PathTestResultPanel.jsx'
import { NoiseCategoryBadge } from '../components/world/noise/NoiseDestinationsTable.jsx'
import { ConfirmDeleteModal } from '../components/ui/ConfirmDeleteModal.jsx'
import { CategoryCombobox } from '../components/ui/CategoryCombobox.jsx'

// ── Iconos SVG inline ─────────────────────────────────────────────────────────

function IconPlus({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function IconEdit({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  )
}

function IconPlay({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  )
}

function IconCopy({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function IconTrash({ size = 13 }) {
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

function IconRefresh({ size = 11 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 .49-3.51" />
    </svg>
  )
}

function IconSearch({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  )
}

function IconCheck({ size = 9 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function IconInfo({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="8" strokeWidth="3" />
      <line x1="12" y1="12" x2="12" y2="16" />
    </svg>
  )
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

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
          {[1, 2, 3, 4, 5].map(i => (
            <tr key={i}>
              {[200, 100, 40, 40, 60, 100].map((w, j) => (
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

// ── Modal Crear Plantilla ─────────────────────────────────────────────────────

function NewTemplateModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    slug: '', label: '', category: null,
    url_pattern: '', navigation_weight: 1.0, is_safe: true,
  })
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState({})

  function validate() {
    const e = {}
    if (!form.slug.trim()) e.slug = 'El identificador es obligatorio'
    else if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(form.slug.trim()))
      e.slug = 'Debe ser kebab-case: letras minúsculas, dígitos y guiones'
    if (!form.label.trim()) e.label = 'El nombre es obligatorio'
    if (!form.url_pattern.trim()) e.url_pattern = 'La URL pattern es obligatoria'
    if (form.navigation_weight < 0.1 || form.navigation_weight > 5.0)
      e.navigation_weight = 'Entre 0.1 y 5.0'
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setSaving(true)
    setErrors({})
    try {
      const created = await api.createRouteTemplate({
        ...form,
        slug: form.slug.trim(),
        label: form.label.trim(),
        url_pattern: form.url_pattern.trim(),
      })
      showToast('Plantilla creada correctamente')
      onCreated(created)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) setErrors({ slug: err.detail })
        else setErrors({ _global: err.detail })
      } else {
        setErrors({ _global: 'Error de red' })
      }
    } finally {
      setSaving(false)
    }
  }

  // Cerrar con ESC
  useEffect(() => {
    function handler(e) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const inputStyle = (hasErr) => ({
    width: '100%', padding: '6px 10px',
    border: `1px solid ${hasErr ? 'var(--danger)' : 'var(--border-strong)'}`,
    borderRadius: 'var(--radius-sm)',
    background: 'var(--surface)', color: 'var(--text)',
    fontFamily: 'inherit', fontSize: '13px',
    boxSizing: 'border-box',
  })

  const labelStyle = {
    display: 'block', fontSize: '12px', fontWeight: 500,
    color: 'var(--text-secondary)', marginBottom: '4px',
  }

  const errorStyle = { fontSize: '11px', color: 'var(--danger)', marginTop: '3px', display: 'block' }

  return (
    <>
      {/* Overlay */}
      <div
        aria-hidden="true"
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,0.4)', zIndex: 500,
        }}
      />
      {/* Modal */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-tpl-title"
        style={{
          position: 'fixed',
          top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-lg)',
          padding: '24px 28px',
          width: 'min(520px, 95vw)',
          zIndex: 600,
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
      >
        <h2 id="new-tpl-title" style={{ fontSize: '17px', fontWeight: 600, marginBottom: '6px' }}>
          Nueva plantilla
        </h2>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px' }}>
          Define una ruta reutilizable. El identificador es permanente y no se puede cambiar tras la creación.
        </p>

        <form onSubmit={handleSubmit}>
          {errors._global && (
            <p role="alert" style={{ ...errorStyle, marginBottom: '12px', padding: '8px', background: 'var(--danger-subtle)', borderRadius: 'var(--radius-sm)' }}>
              {errors._global}
            </p>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
            {/* Identificador (slug) */}
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={labelStyle}>Identificador <span style={{ color: 'var(--danger)' }}>*</span></label>
              <input
                type="text"
                placeholder="rally-point-view"
                value={form.slug}
                onChange={e => setForm(f => ({ ...f, slug: e.target.value }))}
                style={{ ...inputStyle(!!errors.slug), fontFamily: 'var(--font-mono)' }}
                autoFocus
                aria-describedby={errors.slug ? 'err-slug' : undefined}
              />
              {errors.slug && <span id="err-slug" role="alert" style={errorStyle}>{errors.slug}</span>}
              <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', display: 'block', marginTop: '3px' }}>
                Kebab-case, solo minúsculas, dígitos y guiones. Inmutable tras la creación.
              </span>
            </div>

            {/* Nombre (label) */}
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={labelStyle}>Nombre <span style={{ color: 'var(--danger)' }}>*</span></label>
              <input
                type="text"
                placeholder="Rally Point — ver edificio"
                value={form.label}
                onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
                style={inputStyle(!!errors.label)}
                aria-describedby={errors.label ? 'err-label' : undefined}
              />
              {errors.label && <span id="err-label" role="alert" style={errorStyle}>{errors.label}</span>}
            </div>

            {/* Categoría */}
            <div>
              <label style={labelStyle}>Categoría</label>
              <CategoryCombobox
                value={form.category}
                onChange={(slug) => setForm(f => ({ ...f, category: slug }))}
                id="new-template-category"
              />
            </div>

            {/* Peso */}
            <div>
              <label style={labelStyle}>Peso inicial</label>
              <input
                type="number" min="0.1" max="5" step="0.1"
                value={form.navigation_weight}
                onChange={e => setForm(f => ({ ...f, navigation_weight: parseFloat(e.target.value) || 1.0 }))}
                style={{ ...inputStyle(!!errors.navigation_weight), width: '100px', fontFamily: 'var(--font-mono)' }}
                aria-describedby={errors.navigation_weight ? 'err-weight' : undefined}
              />
              {errors.navigation_weight && <span id="err-weight" role="alert" style={errorStyle}>{errors.navigation_weight}</span>}
            </div>

            {/* URL pattern */}
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={labelStyle}>URL pattern <span style={{ color: 'var(--danger)' }}>*</span></label>
              <input
                type="text"
                placeholder="/build.php?gid=13"
                value={form.url_pattern}
                onChange={e => setForm(f => ({ ...f, url_pattern: e.target.value }))}
                style={{ ...inputStyle(!!errors.url_pattern), fontFamily: 'var(--font-mono)' }}
                aria-describedby={errors.url_pattern ? 'err-url' : undefined}
              />
              {errors.url_pattern && <span id="err-url" role="alert" style={errorStyle}>{errors.url_pattern}</span>}
            </div>

            {/* is_safe */}
            <div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '13px' }}>
                <input
                  type="checkbox" checked={form.is_safe}
                  onChange={e => setForm(f => ({ ...f, is_safe: e.target.checked }))}
                  style={{ width: '16px', height: '16px' }}
                />
                Marcar como segura
              </label>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
            <button
              type="button" onClick={onClose}
              style={{
                height: '34px', padding: '0 14px',
                border: '1px solid var(--border-strong)',
                background: 'var(--surface)', color: 'var(--text)',
                borderRadius: 'var(--radius-sm)', fontFamily: 'inherit', fontSize: '13px', cursor: 'pointer',
              }}
            >
              Cancelar
            </button>
            <button
              type="submit" disabled={saving}
              style={{
                height: '34px', padding: '0 16px',
                border: 'none',
                background: saving ? 'var(--surface-2)' : 'var(--btn-primary-bg)',
                color: saving ? 'var(--text-disabled)' : 'var(--btn-primary-text)',
                borderRadius: 'var(--radius-sm)', fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
                cursor: saving ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', gap: '6px',
              }}
            >
              {saving && <Spinner size={12} />}
              {saving ? 'Creando…' : 'Crear plantilla'}
            </button>
          </div>
        </form>
      </div>
    </>
  )
}

// ── Modal Clonar a Mundo ──────────────────────────────────────────────────────

function CloneToWorldModal({ template, worlds, onClose, onCloned }) {
  const [worldId, setWorldId] = useState('')
  const [force, setForce] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null) // respuesta del servidor

  async function handleClone() {
    if (!worldId) return
    setLoading(true)
    setResult(null)
    try {
      const res = await api.cloneRouteTemplate(template.id, parseInt(worldId), force)
      setResult({ ok: true, data: res })
      showToast(
        res.result === 'already_exists'
          ? 'La plantilla ya estaba clonada en ese mundo'
          : 'Plantilla clonada correctamente'
      )
      onCloned?.(res)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const detail = typeof err.detail === 'object' ? err.detail : { message: err.detail }
        setResult({ ok: false, conflict: true, detail })
      } else {
        setResult({ ok: false, error: err instanceof ApiError ? err.detail : 'Error de red' })
      }
    } finally {
      setLoading(false)
    }
  }

  // ESC cierra
  useEffect(() => {
    function handler(e) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <>
      <div aria-hidden="true" onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 500 }}
      />
      <div
        role="dialog" aria-modal="true" aria-labelledby="clone-modal-title"
        style={{
          position: 'fixed', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)',
          padding: '24px 28px', width: 'min(480px, 95vw)', zIndex: 600,
          maxHeight: '90vh', overflowY: 'auto',
        }}
      >
        <h2 id="clone-modal-title" style={{ fontSize: '17px', fontWeight: 600, marginBottom: '6px' }}>
          Clonar plantilla a mundo
        </h2>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px', lineHeight: 1.5 }}>
          Elige el mundo destino. Se creará una copia independiente de{' '}
          <strong>{template.slug}</strong> en ese mundo como <code style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>noise_destination</code>.
        </p>

        {/* Selector de mundo */}
        <div style={{ marginBottom: '14px' }}>
          <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '5px' }}>
            Mundo destino
          </label>
          <select
            value={worldId}
            onChange={e => { setWorldId(e.target.value); setResult(null) }}
            style={{
              width: '100%', padding: '8px 12px',
              border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: worldId ? 'var(--text)' : 'var(--text-tertiary)',
              fontFamily: 'inherit', fontSize: '13px', cursor: 'pointer',
            }}
            aria-label="Seleccionar mundo destino para clonar"
          >
            <option value="">— Seleccionar mundo —</option>
            {worlds.map(w => (
              <option key={w.id} value={w.id}>
                {w.server_url} {w.account_email ? `(${w.account_email})` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Opción force */}
        <div style={{ marginBottom: '14px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'var(--text-secondary)', cursor: 'pointer', userSelect: 'none' }}>
            <input
              type="checkbox" checked={force}
              onChange={e => setForce(e.target.checked)}
              style={{ width: '15px', height: '15px', cursor: 'pointer', accentColor: 'var(--accent)' }}
              aria-label="Sobreescribir si ya existe un destino con la misma URL"
            />
            Sobreescribir si ya existe (force=true)
          </label>
          <p style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '4px', paddingInlineStart: '23px', lineHeight: 1.4 }}>
            Si el mundo ya tiene un destino con la misma URL pattern, lo reemplaza. Úsalo solo si sabes que el conflicto es intencional.
          </p>
        </div>

        {/* Resultado */}
        {result && (
          <div style={{
            border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
            overflow: 'hidden', marginTop: '8px', marginBottom: '14px',
          }}>
            <div style={{
              background: 'var(--surface-2)', padding: '8px 12px',
              fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)',
              textTransform: 'uppercase', letterSpacing: '0.04em',
              borderBottom: '1px solid var(--border)',
            }}>
              Resultado
            </div>
            <div style={{ padding: '10px 12px', fontSize: '13px' }}>
              {result.ok ? (
                <span style={{ color: result.data?.result === 'already_exists' ? 'var(--text-secondary)' : 'var(--success)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {result.data?.result === 'already_exists' ? 'ℹ Ya existía · dest #' + result.data.destination_id : '✓ Clonado · dest #' + result.data?.destination_id}
                </span>
              ) : result.conflict ? (
                <span style={{ color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  ⚠ Conflicto — {result.detail?.message ?? 'Ya existe un destino con esa URL'}
                  {result.detail?.conflicting_destination_id && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                      · dest #{result.detail.conflicting_destination_id}
                    </span>
                  )}
                </span>
              ) : (
                <span style={{ color: 'var(--danger)' }}>{result.error}</span>
              )}
            </div>
          </div>
        )}

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
          <button
            type="button" onClick={onClose}
            style={{
              height: '34px', padding: '0 14px',
              border: '1px solid var(--border-strong)',
              background: 'var(--surface)', color: 'var(--text)',
              borderRadius: 'var(--radius-sm)', fontFamily: 'inherit', fontSize: '13px', cursor: 'pointer',
            }}
          >
            Cancelar
          </button>
          <button
            type="button" onClick={handleClone}
            disabled={!worldId || loading}
            style={{
              height: '34px', padding: '0 16px',
              border: 'none',
              background: (!worldId || loading) ? 'var(--surface-2)' : 'var(--btn-primary-bg)',
              color: (!worldId || loading) ? 'var(--text-disabled)' : 'var(--btn-primary-text)',
              borderRadius: 'var(--radius-sm)', fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
              cursor: (!worldId || loading) ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', gap: '6px',
            }}
            aria-label="Confirmar clonado al mundo seleccionado"
          >
            {loading && <Spinner size={12} />}
            {loading ? 'Clonando…' : 'Clonar plantilla'}
          </button>
        </div>
      </div>
    </>
  )
}

// ── Panel "Probar ruta" ───────────────────────────────────────────────────────

function TestRoutePanel({ template, worlds, onClose }) {
  const [worldId, setWorldId] = useState('')
  const [pathIndex, setPathIndex] = useState(0)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [durationMs, setDurationMs] = useState(null)
  const [apiError, setApiError] = useState(null)
  const closeRef = useRef(null)

  const paths = template?.paths ?? []
  const hasPaths = paths.length > 0
  const currentPath = paths[pathIndex]

  async function handleTest() {
    if (!worldId || !hasPaths) return
    setLoading(true)
    setResult(null)
    setApiError(null)
    const t0 = Date.now()
    try {
      const res = await api.testRouteTemplate(template.id, {
        world_id: parseInt(worldId),
        path_index: pathIndex,
      })
      setDurationMs(Date.now() - t0)
      setResult(res)
    } catch (err) {
      if (err instanceof ApiError) {
        setApiError(err.detail)
      } else {
        setApiError('Error de red')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)', overflow: 'hidden',
      marginTop: '16px',
    }}>
      {/* Cabecera */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '8px',
        padding: '10px 16px', background: 'var(--surface-2)',
        borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ fontSize: '13px', fontWeight: 600, flex: 1 }}>
          Probar ruta en Chrome real
        </span>
        <button
          type="button" onClick={onClose}
          aria-label="Cerrar panel de prueba"
          style={{
            width: '28px', height: '28px', border: 'none', background: 'transparent',
            cursor: 'pointer', color: 'var(--text-secondary)', borderRadius: 'var(--radius-sm)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          ×
        </button>
      </div>

      {/* Aviso: plantilla sin rutas → nada que probar (EC-RT05) */}
      {!hasPaths && (
        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', padding: '12px 16px 0', margin: 0 }}>
          Esta plantilla no tiene rutas definidas, así que no hay nada que probar.
          Añade al menos una ruta (con sus pasos) editando la plantilla antes de ejecutar el test.
        </p>
      )}

      {/* Controles */}
      <div style={{ padding: '14px 16px', display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        {/* Mundo */}
        <div style={{ flex: '1 1 180px' }}>
          <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '4px' }}>
            Mundo
          </label>
          <select
            value={worldId}
            onChange={e => setWorldId(e.target.value)}
            style={{
              width: '100%', padding: '6px 10px',
              border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: worldId ? 'var(--text)' : 'var(--text-tertiary)',
              fontFamily: 'inherit', fontSize: '12px', cursor: 'pointer',
            }}
            aria-label="Seleccionar mundo para el test"
          >
            <option value="">— Elegir mundo —</option>
            {worlds.map(w => (
              <option key={w.id} value={w.id}>
                {w.server_url} {w.account_email ? `(${w.account_email})` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Path index (solo si hay más de 1 path) */}
        {paths.length > 1 && (
          <div style={{ flex: '0 0 120px' }}>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '4px' }}>
              Ruta (índice)
            </label>
            <select
              value={pathIndex}
              onChange={e => setPathIndex(parseInt(e.target.value))}
              style={{
                width: '100%', padding: '6px 10px',
                border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)', color: 'var(--text)',
                fontFamily: 'inherit', fontSize: '12px', cursor: 'pointer',
              }}
              aria-label="Seleccionar índice de ruta a probar"
            >
              {paths.map((p, i) => (
                <option key={i} value={i}>{i}: {p.label ?? p.origin}</option>
              ))}
            </select>
          </div>
        )}

        {/* Botón */}
        <button
          type="button" onClick={handleTest}
          disabled={!worldId || loading || !hasPaths}
          style={{
            height: '34px', padding: '0 14px',
            border: 'none',
            background: (!worldId || loading || !hasPaths) ? 'var(--surface-2)' : 'var(--btn-primary-bg)',
            color: (!worldId || loading || !hasPaths) ? 'var(--text-disabled)' : 'var(--btn-primary-text)',
            borderRadius: 'var(--radius-sm)', fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
            cursor: (!worldId || loading || !hasPaths) ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', gap: '6px',
          }}
          aria-label="Ejecutar test de la ruta"
        >
          {loading ? <Spinner size={12} /> : <IconPlay size={12} />}
          {loading ? 'Probando…' : 'Ejecutar'}
        </button>
      </div>

      {/* Error de API */}
      {apiError && (
        <p role="alert" style={{ fontSize: '12px', color: 'var(--danger)', padding: '0 16px 12px', margin: 0 }}>
          {apiError}
        </p>
      )}

      {/* Resultado */}
      {result && (
        <PathTestResultPanel
          result={result}
          pathSteps={currentPath?.steps ?? []}
          durationMs={durationMs}
          onClose={() => setResult(null)}
          closeRef={closeRef}
        />
      )}
    </div>
  )
}

// ── Panel Re-sync ──────────────────────────────────────────────────────────────

function ResyncPanel({ template, worlds }) {
  const [syncingWorld, setSyncingWorld] = useState(null)
  const [syncResults, setSyncResults] = useState({}) // worldId → { ok, result, error }

  // Mundos que tienen esta plantilla clonada
  // Nota: la información de qué mundos tienen la plantilla se obtendría desde
  // /worlds/{id}/noise/destinations con template_id filtrado. Por simplicidad
  // en esta versión los mostramos con el selector de mundos disponibles.
  // TODO: cargar desde API si hay endpoint de listado de instancias por plantilla.

  async function handleSync(worldId) {
    setSyncingWorld(worldId)
    try {
      const res = await api.syncRouteTemplate(template.id, worldId)
      setSyncResults(prev => ({
        ...prev,
        [worldId]: { ok: true, result: res.result, destinationId: res.destination_id },
      }))
      showToast(
        res.result === 'synced'
          ? 'Instancia re-sincronizada correctamente'
          : 'Instancia creada (no existía en ese mundo)'
      )
    } catch (err) {
      setSyncResults(prev => ({
        ...prev,
        [worldId]: { ok: false, error: err instanceof ApiError ? err.detail : 'Error de red' },
      }))
    } finally {
      setSyncingWorld(null)
    }
  }

  if (!worlds.length) {
    return (
      <div style={{ padding: '16px', color: 'var(--text-tertiary)', fontSize: '13px' }}>
        No hay mundos configurados para sincronizar.
      </div>
    )
  }

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)', overflow: 'hidden', marginTop: '16px',
    }}>
      <div style={{
        background: 'var(--surface-2)', padding: '10px 16px',
        fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)',
        textTransform: 'uppercase', letterSpacing: '0.04em',
        borderBottom: '1px solid var(--border)',
      }}>
        Instancias clonadas — Re-sincronizar
      </div>
      {worlds.map(w => {
        const sr = syncResults[w.id]
        const isSyncing = syncingWorld === w.id
        return (
          <div key={w.id} style={{
            display: 'flex', alignItems: 'center', gap: '12px',
            padding: '12px 16px', borderBottom: '1px solid var(--border)',
            fontSize: '13px',
          }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 500 }}>{w.server_url}</div>
              {sr && (
                <div style={{
                  fontSize: '11px', marginTop: '2px',
                  color: sr.ok ? 'var(--success)' : 'var(--danger)',
                }}>
                  {sr.ok
                    ? (sr.result === 'synced' ? '✓ Sincronizado' : '✓ Creado (dest #' + sr.destinationId + ')')
                    : '✕ ' + sr.error
                  }
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={() => handleSync(w.id)}
              disabled={isSyncing}
              style={{
                display: 'flex', alignItems: 'center', gap: '5px',
                height: '30px', padding: '0 12px',
                border: '1px solid var(--border-strong)',
                background: 'var(--surface)', color: 'var(--text)',
                borderRadius: 'var(--radius-sm)', fontFamily: 'inherit', fontSize: '11px',
                cursor: isSyncing ? 'not-allowed' : 'pointer',
                opacity: isSyncing ? 0.6 : 1,
              }}
              aria-label={`Re-sincronizar instancia en ${w.server_url}`}
            >
              {isSyncing ? <Spinner size={10} /> : <IconRefresh size={11} />}
              Sincronizar
            </button>
          </div>
        )
      })}
    </div>
  )
}

// ── Fila de la tabla de plantillas ────────────────────────────────────────────

function TemplateRow({ tpl, catLabel, catColor, onEdit, onTest, onClone, onDelete, editBtnRef }) {
  const totalSteps = (tpl.paths ?? []).reduce((acc, p) => acc + (p.steps?.length ?? 0), 0)
  const pathsCount = tpl.paths_count ?? (tpl.paths?.length ?? 0)

  const tdBase = {
    padding: '10px 12px',
    borderBottom: '1px solid var(--border)',
    verticalAlign: 'middle',
    fontSize: '13px',
  }

  const btnIcon = {
    width: '30px', height: '30px', minWidth: '30px', minHeight: '30px',
    border: 'none', background: 'transparent',
    borderRadius: 'var(--radius-sm)', cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: 'var(--text-tertiary)',
    transition: 'background var(--dur-fast), color var(--dur-fast)',
    padding: 0,
  }

  return (
    <tr
      style={{ cursor: 'pointer' }}
      className="rt-tpl-row"
      onClick={() => onEdit(tpl)}
      onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onEdit(tpl)}
      tabIndex={0}
      role="row"
    >
      {/* Nombre / Identificador / URL */}
      <td role="cell" style={tdBase}>
        <button
          ref={editBtnRef}
          type="button"
          onClick={(e) => { e.stopPropagation(); onEdit(tpl) }}
          style={{
            appearance: 'none', border: 'none', background: 'transparent',
            padding: 0, cursor: 'pointer', textAlign: 'start', fontFamily: 'inherit',
            color: 'var(--accent-text)', fontWeight: 500, fontSize: '14px',
            display: 'block',
          }}
          aria-label={`Abrir plantilla ${tpl.slug}`}
        >
          {tpl.label}
        </button>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
          {tpl.slug}
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: '11px',
          color: tpl.url_pattern?.startsWith('http') ? 'var(--accent-text)' : 'var(--text-tertiary)',
          fontStyle: tpl.url_pattern?.startsWith('http') ? 'normal' : undefined,
          marginTop: '1px',
        }}>
          {tpl.url_pattern}
        </div>
      </td>

      {/* Categoría — badge dinámico con datos del catálogo */}
      <td role="cell" style={tdBase}>
        <NoiseCategoryBadge label={catLabel} color={catColor} />
      </td>

      {/* Pasos — P2, oculto en móvil */}
      <td role="cell" style={{ ...tdBase, textAlign: 'end', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}
        className="rt-col-steps">
        <span style={{ color: pathsCount === 0 ? 'var(--text-tertiary)' : 'var(--text)' }}>
          {pathsCount}
        </span>
      </td>

      {/* Peso — P2, oculto en móvil */}
      <td role="cell" style={{ ...tdBase, textAlign: 'end', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}
        className="rt-col-weight">
        {tpl.navigation_weight}
      </td>

      {/* Estado — P2, oculto en móvil */}
      <td role="cell" style={{ ...tdBase, textAlign: 'center' }} className="rt-col-status">
        {tpl.is_safe ? (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '4px',
            padding: '2px 8px', borderRadius: 'var(--radius-full)',
            fontSize: '11px', fontWeight: 500,
            background: 'var(--success-subtle)', color: 'var(--success)',
            whiteSpace: 'nowrap',
          }}>
            <IconCheck size={9} /> Segura
          </span>
        ) : (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '4px',
            padding: '2px 8px', borderRadius: 'var(--radius-full)',
            fontSize: '11px', fontWeight: 500,
            background: 'var(--surface-2)', color: 'var(--text-tertiary)',
            whiteSpace: 'nowrap',
          }}>
            Atención
          </span>
        )}
      </td>

      {/* Acciones */}
      <td role="cell" style={{ ...tdBase, width: '136px', textAlign: 'end' }}
        onClick={e => e.stopPropagation()}
        onKeyDown={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '2px', justifyContent: 'flex-end' }}>
          {/* Editar */}
          <button
            type="button" onClick={() => onEdit(tpl)}
            title="Editar plantilla"
            aria-label={`Editar ${tpl.slug}`}
            style={btnIcon}
            className="rt-btn-icon"
          >
            <IconEdit />
          </button>
          {/* Probar */}
          <button
            type="button" onClick={() => onTest(tpl)}
            title="Probar ruta en Chrome real"
            aria-label={`Probar ${tpl.slug}`}
            style={btnIcon}
            className="rt-btn-icon"
          >
            <IconPlay />
          </button>
          {/* Clonar */}
          <button
            type="button" onClick={() => onClone(tpl)}
            title="Clonar a mundo"
            aria-label={`Clonar ${tpl.slug} a un mundo`}
            style={btnIcon}
            className="rt-btn-icon"
          >
            <IconCopy />
          </button>
          {/* Borrar */}
          <button
            type="button" onClick={() => onDelete(tpl)}
            title="Eliminar plantilla"
            aria-label={`Eliminar ${tpl.slug}`}
            style={btnIcon}
            className="rt-btn-icon rt-btn-icon-danger"
          >
            <IconTrash />
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── RouteTemplatesPage ────────────────────────────────────────────────────────

export function RouteTemplatesPage() {
  const { t } = useI18n()

  // ─── Estado principal ────────────────────────────────────────────────────────
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showSeedBanner, setShowSeedBanner] = useState(false)

  // ─── Catálogo de categorías (para cruzar con las plantillas al renderizar) ───
  const [categories, setCategories] = useState([]) // [{slug, label, color, is_default}]

  // ─── Filtros ─────────────────────────────────────────────────────────────────
  const [search, setSearch] = useState('')
  const [filterCategory, setFilterCategory] = useState('')

  // ─── Mundos disponibles (para modal de clonar / panel de test) ───────────────
  const [worlds, setWorlds] = useState([])

  // ─── UI Panels / Modals ───────────────────────────────────────────────────────
  const [showNewModal, setShowNewModal] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerTpl, setDrawerTpl] = useState(null) // template activo en el drawer
  const [cloneTarget, setCloneTarget] = useState(null) // template para modal clonar
  const [testTarget, setTestTarget] = useState(null)   // template para panel test
  const [resyncTarget, setResyncTarget] = useState(null) // template para panel resync
  const [deleteTarget, setDeleteTarget] = useState(null) // template para confirmación borrado
  const [deleting, setDeleting] = useState(false)

  // Refs para devolver el foco
  const drawerTriggerRef = useRef(null)
  const editBtnRefs = useRef({})

  // ─── Carga inicial ────────────────────────────────────────────────────────────

  const loadTemplates = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.listRouteTemplates({ include_paths: true })
      setTemplates(data ?? [])
      // Mostrar banner seed si hay entre 1 y 25 plantillas (rango del seed inicial)
      if (data?.length > 0 && data.length <= 25) {
        setShowSeedBanner(true)
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Error de red al cargar las plantillas')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadWorlds = useCallback(async () => {
    try {
      // Cargamos todas las cuentas y luego todos sus mundos para el selector
      const accounts = await api.getAccounts()
      const worldPromises = accounts.map(acc => api.getWorlds(acc.id).then(ws =>
        ws.map(w => ({ ...w, account_email: acc.email }))
      ))
      const worldArrays = await Promise.all(worldPromises)
      setWorlds(worldArrays.flat())
    } catch {
      // Si falla, los selectores quedan vacíos (no es crítico)
    }
  }, [])

  // Carga del catálogo de categorías (independiente de las plantillas)
  const loadCategories = useCallback(async () => {
    try {
      const data = await api.listCategories()
      setCategories(Array.isArray(data) ? data : [])
    } catch {
      // No es crítico: si falla, los badges muestran solo el slug
    }
  }, [])

  useEffect(() => {
    loadTemplates()
    loadWorlds()
    loadCategories()
  }, [loadTemplates, loadWorlds, loadCategories])

  // Helper: dada una plantilla, devuelve {label, color} de su categoría
  function getCatMeta(tpl) {
    const slug = tpl.category_slug ?? tpl.category ?? null
    if (!slug) return { label: 'Sin categoría', color: null }
    const cat = categories.find(c => c.slug === slug)
    return cat ? { label: cat.label, color: cat.color ?? null } : { label: slug, color: null }
  }

  // ─── Filtrado ─────────────────────────────────────────────────────────────────

  const filtered = templates.filter(t => {
    const tplSlug = t.category_slug ?? t.category ?? null
    if (filterCategory && tplSlug !== filterCategory) return false
    if (search) {
      const q = search.toLowerCase()
      return t.label?.toLowerCase().includes(q) || t.slug?.toLowerCase().includes(q)
    }
    return true
  })

  // ─── Callbacks de mutación ────────────────────────────────────────────────────

  function handleCreated(tpl) {
    setTemplates(prev => [tpl, ...prev])
    setShowNewModal(false)
  }

  function handleTemplateSaved(updated) {
    setTemplates(prev => prev.map(t => t.id === updated.id ? { ...t, ...updated } : t))
    setDrawerTpl(updated)
  }

  async function handleConfirmDelete() {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.deleteRouteTemplate(deleteTarget.id)
      setTemplates(prev => prev.filter(t => t.id !== deleteTarget.id))
      showToast('Plantilla eliminada')
      if (drawerTpl?.id === deleteTarget.id) setDrawerOpen(false)
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : 'Error al eliminar')
    } finally {
      setDeleting(false)
      setDeleteTarget(null)
    }
  }

  function handleOpenDrawer(tpl) {
    setDrawerTpl(tpl)
    setDrawerOpen(true)
  }

  function handleCloseDrawer() {
    setDrawerOpen(false)
    drawerTriggerRef.current?.focus()
  }

  // ─── Estilos comunes ──────────────────────────────────────────────────────────

  const thStyle = {
    fontSize: '11px', fontWeight: 600, letterSpacing: '0.04em',
    textTransform: 'uppercase', color: 'var(--text-secondary)',
    padding: '8px 12px', textAlign: 'start',
    borderBottom: '1px solid var(--border)',
    background: 'var(--surface-2)', whiteSpace: 'nowrap',
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: '960px' }}>

      {/* Estilos responsivos y hover */}
      <style>{`
        @media (max-width: 767px) {
          .rt-col-steps, .rt-col-weight, .rt-col-status { display: none !important; }
          .rt-th-steps, .rt-th-weight, .rt-th-status { display: none !important; }
        }
        .rt-tpl-row:hover td { background: var(--surface-2); }
        .rt-btn-icon:hover { background: var(--surface-2); color: var(--text); }
        .rt-btn-icon-danger:hover { background: var(--danger-subtle) !important; color: var(--danger) !important; }
      `}</style>

      {/* ── BLOQUE A — Cabecera ─────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: '16px', flexWrap: 'wrap', marginBottom: '24px',
      }}>
        <div>
          <h1 style={{
            fontSize: '28px', fontWeight: 600, letterSpacing: '-0.02em',
            color: 'var(--text)', margin: 0,
          }}>
            Catálogo de rutas
          </h1>
          <p style={{
            fontSize: '14px', color: 'var(--text-secondary)',
            marginTop: '6px', maxWidth: '600px', lineHeight: 1.5, marginBottom: 0,
          }}>
            Plantillas globales de navegación de ruido. Defínelas una vez y clónalas a cualquier mundo.
            El bot las recorre como un usuario humano para despitar la detección.
          </p>
        </div>
        <div style={{ flexShrink: 0, paddingTop: '4px' }}>
          <button
            type="button"
            onClick={() => setShowNewModal(true)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              padding: '7px 16px', border: 'none',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--btn-primary-bg)', color: 'var(--btn-primary-text)',
              fontFamily: 'inherit', fontSize: '13px', fontWeight: 600,
              cursor: 'pointer', whiteSpace: 'nowrap',
              minHeight: '44px',
            }}
            aria-label="Crear nueva plantilla"
          >
            <IconPlus size={14} />
            Nueva plantilla
          </button>
        </div>
      </div>

      {/* ── BLOQUE I — Banner seed inicial ──────────────────────────────────── */}
      {showSeedBanner && !loading && !error && (
        <div style={{
          background: 'var(--info-subtle)', border: '1px solid var(--info)',
          borderRadius: 'var(--radius-md)', padding: '14px 18px',
          display: 'flex', alignItems: 'flex-start', gap: '12px',
          marginBottom: '16px',
        }}
          role="status"
          aria-label="Plantillas del seed cargadas"
        >
          <span style={{ fontSize: '18px', flexShrink: 0, marginTop: '1px' }} aria-hidden="true">
            <IconInfo size={18} />
          </span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--info)', marginBottom: '3px' }}>
              Catálogo inicial cargado
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Se han cargado ~{templates.length} plantillas de navegación pre-definidas al arrancar el servidor.
              Edítalas o añade las tuyas propias.
            </div>
          </div>
          <button
            type="button"
            onClick={() => setShowSeedBanner(false)}
            aria-label="Cerrar aviso"
            style={{
              border: 'none', background: 'transparent', cursor: 'pointer',
              color: 'var(--text-tertiary)', fontSize: '16px', flexShrink: 0,
              lineHeight: 1, padding: '2px 4px',
            }}
          >
            ×
          </button>
        </div>
      )}

      {/* ── BLOQUE B — Barra de filtros ──────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap',
        marginBottom: '12px',
      }}>
        {/* Búsqueda de texto libre */}
        <div style={{ position: 'relative', flex: '1 1 200px', maxWidth: '320px' }}>
          <span style={{
            position: 'absolute', left: '9px', top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-tertiary)', pointerEvents: 'none',
          }}>
            <IconSearch size={13} />
          </span>
          <input
            type="search"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por nombre o identificador…"
            style={{
              width: '100%', paddingInlineStart: '30px', padding: '6px 10px',
              paddingLeft: '30px',
              border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)',
              background: 'var(--surface)', color: 'var(--text)',
              fontFamily: 'inherit', fontSize: '12px',
              boxSizing: 'border-box',
            }}
            aria-label="Buscar plantillas por nombre o identificador"
          />
        </div>

        {/* Filtro de categoría — CategoryCombobox en modo solo-selección */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {filterCategory && (
            <button
              type="button"
              aria-label="Quitar filtro de categoría"
              onClick={() => setFilterCategory('')}
              style={{
                border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)', color: 'var(--text-secondary)',
                padding: '0 8px', height: '32px', cursor: 'pointer',
                fontFamily: 'inherit', fontSize: '12px',
                display: 'flex', alignItems: 'center', gap: '4px',
              }}
            >
              × Categoría
            </button>
          )}
          {!filterCategory && (
            <CategoryCombobox
              value={filterCategory || null}
              onChange={(slug) => setFilterCategory(slug ?? '')}
              id="rt-filter-category"
            />
          )}
        </div>

        {/* Contador */}
        {!loading && !error && (
          <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginInlineStart: '4px' }}>
            {filtered.length} {filtered.length === 1 ? 'plantilla' : 'plantillas'}
          </span>
        )}
      </div>

      {/* ── BLOQUE C/D — Tabla de plantillas ─────────────────────────────────── */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)', overflow: 'hidden',
        marginBottom: '16px',
      }}>
        {/* Toolbar de la tabla */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          padding: '12px 16px', borderBottom: '1px solid var(--border)',
          flexWrap: 'wrap',
        }}>
          <span style={{ fontSize: '13px', fontWeight: 600, flex: 1, color: 'var(--text-secondary)' }}>
            Plantillas del catálogo
          </span>
          {!loading && !error && templates.length > 0 && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: '4px',
              padding: '2px 8px', borderRadius: 'var(--radius-full)',
              fontSize: '11px', fontWeight: 500,
              background: 'var(--accent-subtle)', color: 'var(--accent-text)',
              whiteSpace: 'nowrap',
            }}>
              ~{templates.length} seed
            </span>
          )}
        </div>

        {/* Estado: cargando */}
        {loading && (
          <div style={{ padding: '16px' }}>
            <SkeletonTable />
          </div>
        )}

        {/* Estado: error */}
        {!loading && error && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            gap: '12px', padding: '48px 24px', textAlign: 'center',
          }}
            role="alert"
          >
            <p style={{ fontSize: '15px', fontWeight: 600, color: 'var(--danger)', margin: 0 }}>
              Error al cargar las plantillas
            </p>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '340px', lineHeight: 1.5, margin: 0 }}>
              {error}
            </p>
            <button
              type="button" onClick={loadTemplates}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '6px',
                height: '34px', padding: '0 14px',
                border: 'none',
                background: 'var(--btn-primary-bg)', color: 'var(--btn-primary-text)',
                borderRadius: 'var(--radius-sm)', fontFamily: 'inherit', fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              <IconRefresh size={12} /> Reintentar
            </button>
          </div>
        )}

        {/* Estado: vacío (BLOQUE D) */}
        {!loading && !error && templates.length === 0 && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            gap: '12px', padding: '64px 24px', textAlign: 'center',
          }}
            aria-label="Sin plantillas en el catálogo"
          >
            <div style={{ fontSize: '36px', opacity: 0.4 }} aria-hidden="true">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
                <path d="M3 6h18M3 12h12M3 18h8" />
                <circle cx="19" cy="17" r="3" />
                <path d="M21.5 19.5l-1-1" />
              </svg>
            </div>
            <p style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-secondary)', margin: 0 }}>
              Sin plantillas todavía
            </p>
            <p style={{ fontSize: '13px', color: 'var(--text-tertiary)', maxWidth: '340px', lineHeight: 1.5, margin: 0 }}>
              El catálogo está vacío. Crea tu primera plantilla o espera a que se cargue el seed de ~20 plantillas al arrancar el servidor.
            </p>
            <button
              type="button" onClick={() => setShowNewModal(true)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '6px',
                height: '36px', padding: '0 16px',
                border: 'none',
                background: 'var(--btn-primary-bg)', color: 'var(--btn-primary-text)',
                borderRadius: 'var(--radius-sm)', fontFamily: 'inherit', fontSize: '13px', fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              <IconPlus size={14} /> Nueva plantilla
            </button>
          </div>
        )}

        {/* Estado: filtro sin resultados */}
        {!loading && !error && templates.length > 0 && filtered.length === 0 && (
          <div style={{ textAlign: 'center', padding: '48px 24px' }}>
            <p style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px' }}>
              Sin resultados para los filtros actuales
            </p>
            <button
              type="button"
              onClick={() => { setSearch(''); setFilterCategory('') }}
              style={{
                height: '32px', padding: '0 14px',
                border: '1px solid var(--border-strong)',
                background: 'var(--surface)', color: 'var(--text)',
                borderRadius: 'var(--radius-sm)', fontFamily: 'inherit', fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              Limpiar filtros
            </button>
          </div>
        )}

        {/* Tabla con datos (BLOQUE C) */}
        {!loading && !error && filtered.length > 0 && (
          <div style={{ overflowX: 'auto' }}>
            <table
              style={{ width: '100%', borderCollapse: 'collapse' }}
              role="table"
              aria-label="Catálogo de plantillas de ruta"
            >
              <thead>
                <tr>
                  <th scope="col" style={thStyle}>Plantilla</th>
                  <th scope="col" style={thStyle}>Categoría</th>
                  <th scope="col" style={{ ...thStyle, textAlign: 'end' }} className="rt-th-steps rt-col-steps">Pasos</th>
                  <th scope="col" style={{ ...thStyle, textAlign: 'end' }} className="rt-th-weight rt-col-weight">Peso</th>
                  <th scope="col" style={{ ...thStyle, textAlign: 'center' }} className="rt-th-status rt-col-status">Estado</th>
                  <th scope="col" style={{ ...thStyle, textAlign: 'end', width: '136px' }} aria-label="Acciones">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(tpl => {
                  const { label: catLabel, color: catColor } = getCatMeta(tpl)
                  return (
                    <TemplateRow
                      key={tpl.id}
                      tpl={tpl}
                      catLabel={catLabel}
                      catColor={catColor}
                      onEdit={handleOpenDrawer}
                      onTest={(t) => { setTestTarget(t); setResyncTarget(null) }}
                      onClone={(t) => setCloneTarget(t)}
                      onDelete={(t) => setDeleteTarget(t)}
                      editBtnRef={el => { editBtnRefs.current[tpl.id] = el }}
                    />
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Panel "Probar ruta" (BLOQUE G) — inline bajo la tabla ─────────────── */}
      {testTarget && (
        <TestRoutePanel
          template={testTarget}
          worlds={worlds}
          onClose={() => setTestTarget(null)}
        />
      )}

      {/* ── Panel "Re-sync" (BLOQUE H) — inline bajo la tabla ─────────────────── */}
      {resyncTarget && (
        <ResyncPanel template={resyncTarget} worlds={worlds} />
      )}

      {/* ── BLOQUE E — Drawer de edición de plantilla ──────────────────────────── */}
      <NoiseDestinationDrawer
        open={drawerOpen}
        dest={drawerTpl}
        worldId={null}
        onClose={handleCloseDrawer}
        triggerRef={drawerTriggerRef}
        onDestUpdated={handleTemplateSaved}
        origins={null}
        loadingOrigins={false}
        originsError={null}
        onOriginsRefreshed={null}
        onRetryOrigins={null}
        mode="template"
        templateId={drawerTpl?.id}
        onTemplateSaved={handleTemplateSaved}
        onTemplateDeleted={() => {
          setTemplates(prev => prev.filter(t => t.id !== drawerTpl?.id))
          setDrawerOpen(false)
        }}
      />

      {/* ── BLOQUE F — Modal Clonar a Mundo ──────────────────────────────────── */}
      {cloneTarget && (
        <CloneToWorldModal
          template={cloneTarget}
          worlds={worlds}
          onClose={() => setCloneTarget(null)}
          onCloned={() => {
            // No necesitamos actualizar la lista de plantillas, el clon crea una instancia por-mundo
          }}
        />
      )}

      {/* Modal de confirmación de borrado */}
      {deleteTarget && (
        <ConfirmDeleteModal
          title="Eliminar plantilla"
          question={`¿Eliminar la plantilla "${deleteTarget.label}"? Las instancias clonadas en mundos quedarán con template_id = null pero seguirán activas.`}
          warning=""
          onConfirm={handleConfirmDelete}
          onClose={() => setDeleteTarget(null)}
          triggerRef={{ current: editBtnRefs.current[deleteTarget?.id] }}
        />
      )}

      {/* Modal nueva plantilla */}
      {showNewModal && (
        <NewTemplateModal
          onClose={() => setShowNewModal(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  )
}
