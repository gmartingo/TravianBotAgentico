/**
 * IngestTab — Pestaña "Ingresar" del módulo de reportes de oasis.
 *
 * Flujo:
 *  1. Textarea vacío → botón "Analizar" deshabilitado.
 *  2. Texto pegado → "Analizar" habilitado (Cmd+Enter / Ctrl+Enter también lo activa).
 *  3. Durante parseo → textarea readonly, botón con spinner.
 *  4. Parse OK (sin duplicado) → textarea colapsado + preview + botones Guardar/Descartar.
 *  5. Parse OK (con duplicado) → banner ⚠ + preview + botones.
 *  6. Parse error (422) → mensaje inline bajo textarea, textarea recupera foco.
 *  7. Guardar OK (201) → toast, form limpio, foco al textarea.
 *  8. Guardar 409 → error inline bajo el botón Guardar.
 *
 * Props:
 *   onOpenDrawer — (id: number) => void — para abrir el drawer de un reporte existente
 *   lang         — string (idioma activo para formateo)
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api } from '../../api/client.js'
import { Spinner, showToast } from '../ui/uiUtils.jsx'
import { ReportPreview } from './ReportPreview.jsx'

// ── Botón primario monocromo (grafito/claro, plata/oscuro) ──────────────────
function PrimaryBtn({ children, disabled, onClick, loading, style = {} }) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      onClick={onClick}
      style={{
        height: '36px',
        padding: '0 20px',
        background: disabled || loading ? 'var(--surface-2)' : 'var(--btn-primary-bg)',
        color: disabled || loading ? 'var(--text-disabled)' : 'var(--btn-primary-text)',
        border: 'none',
        borderRadius: 'var(--radius-sm)',
        fontSize: '14px',
        fontWeight: 500,
        fontFamily: 'inherit',
        cursor: disabled || loading ? 'not-allowed' : 'pointer',
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        transition: 'background var(--dur-fast), color var(--dur-fast)',
        ...style,
      }}
    >
      {loading && <Spinner size={13} />}
      {children}
    </button>
  )
}

// ── Botón ghost/terciario ───────────────────────────────────────────────────
function GhostBtn({ children, disabled, onClick }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      style={{
        height: '36px',
        padding: '0 16px',
        background: 'transparent',
        color: disabled ? 'var(--text-disabled)' : 'var(--text-secondary)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '14px',
        fontFamily: 'inherit',
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'border-color var(--dur-fast)',
      }}
    >
      {children}
    </button>
  )
}

// ── Bloque de error inline ──────────────────────────────────────────────────
function InlineError({ message }) {
  if (!message) return null
  return (
    <div
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '8px',
        padding: '10px 12px',
        background: 'var(--danger-subtle, color-mix(in srgb, var(--danger) 10%, transparent))',
        border: '1px solid var(--danger)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '13px',
        color: 'var(--text)',
        lineHeight: 1.5,
      }}
    >
      <span aria-hidden="true" style={{ flexShrink: 0, fontWeight: 700, color: 'var(--danger)' }}>✕</span>
      <span>{message}</span>
    </div>
  )
}

export function IngestTab({ onOpenDrawer, lang }) {
  const { t } = useI18n()
  const textareaRef = useRef(null)

  const [text, setText] = useState('')
  const [parsing, setParsing] = useState(false)
  const [parseResult, setParseResult] = useState(null)  // respuesta del backend
  const [parseError, setParseError] = useState(null)    // string de error
  const [textCollapsed, setTextCollapsed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [showFullText, setShowFullText] = useState(false)

  // Foco automático al montar (DA-02)
  useEffect(() => {
    const timer = setTimeout(() => textareaRef.current?.focus(), 80)
    return () => clearTimeout(timer)
  }, [])

  // Atajo Cmd+Enter / Ctrl+Enter (DA accesibilidad)
  const handleKeyDown = useCallback(
    (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        if (!parsing && text.trim()) handleAnalyze()
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [text, parsing]
  )

  function resetForm() {
    setText('')
    setParseResult(null)
    setParseError(null)
    setTextCollapsed(false)
    setShowFullText(false)
    setSaveError(null)
    setTimeout(() => textareaRef.current?.focus(), 60)
  }

  async function handleAnalyze() {
    if (!text.trim() || parsing) return
    setParseError(null)
    setSaveError(null)
    setParseResult(null)
    setParsing(true)
    try {
      const data = await api.parseAttackReport(text)
      setParseResult(data)
      setTextCollapsed(true)
    } catch (err) {
      const msg = err?.detail ?? err?.message ?? t('ar.ingest.error.parse')
      setParseError(msg)
      setTimeout(() => textareaRef.current?.focus(), 60)
    } finally {
      setParsing(false)
    }
  }

  async function handleSave() {
    if (saving || !parseResult) return
    setSaveError(null)
    setSaving(true)
    try {
      await api.saveAttackReport(text)
      showToast(t('ar.ingest.toast.saved'))
      resetForm()
    } catch (err) {
      if (err?.status === 409) {
        setSaveError(t('ar.ingest.error.save409'))
      } else {
        setSaveError(err?.detail ?? t('ar.ingest.error.saveRetry'))
      }
    } finally {
      setSaving(false)
    }
  }

  const hasText = text.trim().length > 0
  const hasPreview = parseResult !== null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '800px' }}>
      {/* ── Sección textarea ──────────────────────────────────────────────── */}
      {hasPreview && textCollapsed ? (
        /* Textarea colapsado (§6.4) */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {!showFullText ? (
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
                color: 'var(--text-tertiary)',
                whiteSpace: 'pre-wrap',
                overflow: 'hidden',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '8px 10px',
                background: 'var(--surface-2)',
              }}
            >
              {text}
            </div>
          ) : (
            <textarea
              value={text}
              readOnly
              style={{
                width: '100%',
                minHeight: '140px',
                resize: 'vertical',
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
                padding: '10px 12px',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-secondary)',
                boxSizing: 'border-box',
              }}
            />
          )}
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <button
              type="button"
              onClick={() => setShowFullText((v) => !v)}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                cursor: 'pointer',
                fontSize: '12px',
                color: 'var(--text-tertiary)',
                fontFamily: 'inherit',
              }}
            >
              {showFullText ? t('ar.ingest.hideFullText') : t('ar.ingest.viewFullText')}
            </button>
            <GhostBtn onClick={resetForm}>
              {t('ar.ingest.analyzeAnother')}
            </GhostBtn>
          </div>
        </div>
      ) : (
        /* Textarea expandido (estado inicial o error) */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <label
            htmlFor="ar-textarea"
            style={{ fontSize: '13px', color: 'var(--text-secondary)', fontWeight: 500 }}
          >
            {t('ar.ingest.label')}
          </label>
          <div style={{ position: 'relative' }}>
            <textarea
              id="ar-textarea"
              ref={textareaRef}
              value={text}
              onChange={(e) => { setText(e.target.value); setParseError(null) }}
              onKeyDown={handleKeyDown}
              readOnly={parsing}
              placeholder={t('ar.ingest.placeholder')}
              rows={8}
              style={{
                width: '100%',
                resize: 'vertical',
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
                padding: '10px 12px',
                background: parsing ? 'var(--surface-2)' : 'var(--surface)',
                border: `1px solid ${parseError ? 'var(--danger)' : 'var(--border-strong)'}`,
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text)',
                outline: 'none',
                transition: 'border-color var(--dur-fast)',
                boxSizing: 'border-box',
              }}
              onFocus={(e) => {
                if (!parseError) e.currentTarget.style.borderColor = 'var(--accent)'
              }}
              onBlur={(e) => {
                if (!parseError) e.currentTarget.style.borderColor = 'var(--border-strong)'
              }}
            />
            {/* Barra de progreso lineal (§6.3) */}
            {parsing && (
              <div
                aria-hidden="true"
                style={{
                  position: 'absolute',
                  bottom: 0,
                  left: 0,
                  right: 0,
                  height: '2px',
                  background: 'var(--accent)',
                  borderRadius: '0 0 var(--radius-sm) var(--radius-sm)',
                  animation: 'indeterminate-progress 1.2s ease-in-out infinite',
                }}
              />
            )}
          </div>

          {/* Error inline de parseo */}
          {parseError && <InlineError message={parseError} />}

          {/* Fila botón + hint de atajo */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            {/* Hint de atajo (P3 — oculto en móvil) */}
            <span
              aria-hidden="true"
              className="hidden sm:block"
              style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}
            >
              {t('ar.ingest.shortcut')}
            </span>
            <PrimaryBtn
              disabled={!hasText || parsing}
              loading={parsing}
              onClick={handleAnalyze}
              title={t('ar.ingest.shortcut')}
            >
              {parsing ? t('ar.ingest.analyzing') : t('ar.ingest.analyze')}
            </PrimaryBtn>
          </div>
        </div>
      )}

      {/* ── Preview del reporte ───────────────────────────────────────────── */}
      {hasPreview && (
        <div
          style={{
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            padding: '16px',
            background: 'var(--surface)',
            animation: 'fade-in-up 220ms ease both',
          }}
        >
          <ReportPreview
            data={parseResult}
            lang={lang}
            onViewExisting={(id) => onOpenDrawer(id)}
            t={t}
          />

          {/* Error al guardar */}
          {saveError && (
            <div style={{ marginTop: '12px' }}>
              <InlineError message={saveError} />
            </div>
          )}

          {/* Botones de acción (§6.4 / §6.5) */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '10px',
              marginTop: '16px',
              paddingTop: '12px',
              borderTop: '1px solid var(--border)',
            }}
          >
            <GhostBtn disabled={saving} onClick={resetForm}>
              {t('ar.ingest.discard')}
            </GhostBtn>
            <PrimaryBtn loading={saving} onClick={handleSave}>
              {saving
                ? t('ar.ingest.saving')
                : parseResult?.already_exists
                  ? t('ar.ingest.saveAnyway')
                  : t('ar.ingest.save')}
            </PrimaryBtn>
          </div>
        </div>
      )}

      {/* Keyframe para la animación de progreso indeterminado y fade */}
      <style>{`
        @keyframes indeterminate-progress {
          0%   { transform: translateX(-100%) scaleX(0.3); }
          50%  { transform: translateX(0%)    scaleX(0.6); }
          100% { transform: translateX(100%)  scaleX(0.3); }
        }
        @keyframes fade-in-up {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @media (prefers-reduced-motion: reduce) {
          .fade-in-up, [style*="fade-in-up"] { animation: none !important; }
          [style*="indeterminate-progress"]  { animation: none !important; }
        }
      `}</style>
    </div>
  )
}
