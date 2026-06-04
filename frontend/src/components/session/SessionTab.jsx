/**
 * SessionTab — Contenedor raíz de la pestaña "Sesión" en WorldSpacePage.
 *
 * Orquesta:
 *  - GET /worlds/:worldId/session          → sessionStatus (polling 15s)
 *  - GET /worlds/:worldId/session/timeline → timelines de 7 días (carga al montar)
 *  - PUT /worlds/:worldId/session/mode     → override manual
 *  - PUT /worlds/:worldId/session/timeline/:weekday → guardar bloques del día
 *
 * Props:
 *  - worldId {number}
 *
 * Estructura visual (spec §6):
 *  1. SessionStatusPanel (siempre visible, P1)
 *  2. SessionOverridePanel (siempre visible, P1)
 *  3. Calendario semanal: título + hint + WeekdaySelector + TimelineBar
 *  4. BlockEditor (visible al seleccionar un día, P2)
 *
 * Spec: docs/design/human-sessions-ui.md
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api, ApiError } from '../../api/client.js'
import { showToast } from '../ui/uiUtils.jsx'
import { SessionStatusPanel } from './SessionStatusPanel.jsx'
import { SessionOverridePanel } from './SessionOverridePanel.jsx'
import { WeekdaySelector } from './WeekdaySelector.jsx'
import { TimelineBar, validateCoverage } from './TimelineBar.jsx'
import { BlockEditor } from './BlockEditor.jsx'

// Obtener día de la semana actual en esquema 0=lun…6=dom
// JavaScript: 0=dom…6=sáb → convertir
function getTodayWeekday() {
  const jsDay = new Date().getDay() // 0=dom
  return jsDay === 0 ? 6 : jsDay - 1
}

// Nombre del día localizado para el título del editor y los toasts
function getDayName(weekday, lang) {
  const date = new Date(2024, 0, 1 + weekday) // 2024-01-01 = lunes
  return new Intl.DateTimeFormat(lang, { weekday: 'long' }).format(date)
}

// Normalizar bloques del API: asegurar que los modos están en minúsculas para la UI
function normalizeBlocks(blocks) {
  return (blocks ?? []).map(b => ({
    ...b,
    mode: b.mode?.toLowerCase() ?? 'disconnected',
  }))
}

export function SessionTab({ worldId }) {
  const { t, lang } = useI18n()

  // ── Estado del status ─────────────────────────────────────────────────────
  const [sessionStatus, setSessionStatus] = useState(null)
  const [statusLoading, setStatusLoading] = useState(true)
  const [statusError, setStatusError] = useState(null)

  // ── Estado de los 7 timelines ─────────────────────────────────────────────
  const [timelines, setTimelines] = useState([])
  const [timelinesLoading, setTimelinesLoading] = useState(true)
  const [timelinesError, setTimelinesError] = useState(null)

  // ── Override loading ──────────────────────────────────────────────────────
  const [overrideLoading, setOverrideLoading] = useState(null) // 'HARDCORE'|'PASIVO'|'DISCONNECTED'|null
  const [cancellingOverride, setCancellingOverride] = useState(false)

  // ── Selección de día y edición ────────────────────────────────────────────
  const [selectedDay, setSelectedDay] = useState(null)
  const [editBlocks, setEditBlocks] = useState(null)
  const [savingBlocks, setSavingBlocks] = useState(false)
  const [blockApiError, setBlockApiError] = useState(null)
  const [copyingDays, setCopyingDays] = useState(false)

  const todayWeekday = getTodayWeekday()
  const editorRef = useRef(null)

  // ── Fetch status ──────────────────────────────────────────────────────────
  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.getWorldSession(worldId)
      setSessionStatus(data)
      setStatusError(null)
    } catch (e) {
      setStatusError(e instanceof ApiError ? e.detail : t('session.status.loadingError'))
    } finally {
      setStatusLoading(false)
    }
  }, [worldId])

  // ── Fetch timelines ───────────────────────────────────────────────────────
  const fetchTimelines = useCallback(async () => {
    setTimelinesLoading(true)
    try {
      const data = await api.getWorldTimeline(worldId)
      setTimelines(data?.timelines ?? [])
      setTimelinesError(null)
    } catch (e) {
      setTimelinesError(e instanceof ApiError ? e.detail : t('session.timeline.loadingError'))
    } finally {
      setTimelinesLoading(false)
    }
  }, [worldId])

  // ── Carga inicial ─────────────────────────────────────────────────────────
  useEffect(() => {
    fetchStatus()
    fetchTimelines()
  }, [worldId])

  // Polling del status cada 15s
  useEffect(() => {
    const id = setInterval(fetchStatus, 15_000)
    return () => clearInterval(id)
  }, [fetchStatus])

  // ── Seleccionar día ───────────────────────────────────────────────────────
  function handleSelectDay(day) {
    setSelectedDay(day)
    setBlockApiError(null)
    const tl = timelines[day]
    if (tl) {
      setEditBlocks(normalizeBlocks(tl.blocks))
    } else {
      setEditBlocks([{ start: '00:00', end: '24:00', mode: 'disconnected' }])
    }
    // Scroll al editor
    setTimeout(() => {
      editorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }, 100)
  }

  // ── Override manual ───────────────────────────────────────────────────────
  async function handleOverride(mode) {
    setOverrideLoading(mode)
    try {
      const resp = await api.putWorldMode(worldId, mode)
      if (resp.already_active) {
        showToast(t('session.override.alreadyActive', { mode: t(`session.mode.${mode.toLowerCase()}`) }))
      } else {
        const time = resp.expires_at
          ? (() => {
              const d = new Date(resp.expires_at)
              return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
            })()
          : '—'
        showToast(t('session.override.applied', {
          mode: t(`session.mode.${mode.toLowerCase()}`),
          time,
        }))
      }
      await fetchStatus()
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('session.status.loadingError'))
    } finally {
      setOverrideLoading(null)
    }
  }

  // ── Cancelar override ─────────────────────────────────────────────────────
  // Borra el override en el backend (DELETE /session/override). El WorldAgent
  // vuelve a seguir el calendario en su próxima iteración. Idempotente: el
  // endpoint responde 204 aunque no hubiera override activo.
  async function handleCancelOverride() {
    setCancellingOverride(true)
    try {
      await api.deleteWorldOverride(worldId)
      showToast(t('session.override.cancel'))
      await fetchStatus()
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('session.status.loadingError'))
    } finally {
      setCancellingOverride(false)
    }
  }

  // ── Guardar bloques de un día ─────────────────────────────────────────────
  async function handleSaveBlocks(blocks) {
    if (selectedDay === null) return
    setSavingBlocks(true)
    setBlockApiError(null)
    try {
      // El backend (enum SessionMode) exige el modo en MAYÚSCULAS: HARDCORE / PASIVO / DISCONNECTED.
      // En la UI los modos viven en minúsculas, así que serializamos al enum antes del PUT.
      const wireBlocks = blocks.map(b => ({ ...b, mode: (b.mode ?? 'disconnected').toUpperCase() }))
      const saved = await api.putWorldTimelineDay(worldId, selectedDay, { blocks: wireBlocks })
      // Actualizar el timeline local con la respuesta del servidor
      setTimelines(prev => prev.map((tl, i) => i === selectedDay ? saved : tl))
      setEditBlocks(normalizeBlocks(saved.blocks))
      const dayLabel = getDayName(selectedDay, lang)
      showToast(t('session.editor.saved', { day: dayLabel }))
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : t('session.editor.saveError')
      setBlockApiError(msg)
    } finally {
      setSavingBlocks(false)
    }
  }

  // ── Copiar el día actual a otros días (presets) ───────────────────────────
  // Aplica los bloques del día en edición a un conjunto de días destino
  // (toda la semana / entre semana / fin de semana) reutilizando el PUT por día.
  async function handleCopyToDays(weekdays) {
    if (selectedDay === null || !editBlocks) return
    // Defensa: el día origen debe cubrir 24h (los botones ya se deshabilitan si no).
    if (!validateCoverage(editBlocks).ok) {
      showToast(t('session.editor.saveError'))
      return
    }
    setCopyingDays(true)
    setBlockApiError(null)
    const wireBlocks = editBlocks.map(b => ({ ...b, mode: (b.mode ?? 'disconnected').toUpperCase() }))
    try {
      // Secuencial a propósito: el backend usa una única conexión SQLite y
      // upsert_timeline abre una transacción; lanzar los PUT en paralelo
      // solaparía transacciones en la misma conexión y daría 500.
      const byDay = new Map()
      for (const wd of weekdays) {
        const saved = await api.putWorldTimelineDay(worldId, wd, { blocks: wireBlocks })
        byDay.set(wd, saved)
      }
      setTimelines(prev => prev.map((tl, i) => byDay.has(i) ? byDay.get(i) : tl))
      // Si el día en edición está incluido, refrescar sus bloques con la respuesta.
      if (byDay.has(selectedDay)) {
        setEditBlocks(normalizeBlocks(byDay.get(selectedDay).blocks))
      }
      showToast(t('session.editor.copied', { n: weekdays.length }))
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('session.editor.copyError'))
    } finally {
      setCopyingDays(false)
    }
  }

  // ── El timeline del día seleccionado (para la barra) ─────────────────────
  const selectedTimeline = selectedDay !== null ? timelines[selectedDay] : null
  const selectedDayLabel = selectedDay !== null ? getDayName(selectedDay, lang) : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

      {/* 1. Panel de estado */}
      <SessionStatusPanel
        status={sessionStatus}
        loading={statusLoading}
        error={statusError}
        onRetry={fetchStatus}
        onCancelOverride={handleCancelOverride}
        cancellingOverride={cancellingOverride}
      />

      {/* 2. Override panel */}
      <SessionOverridePanel
        currentMode={sessionStatus?.mode ?? null}
        overrideMode={sessionStatus?.override?.mode ?? null}
        loading={overrideLoading}
        onOverride={handleOverride}
      />

      {/* 3. Calendario semanal */}
      <div style={cardStyle}>
        <div style={{
          display: 'flex', alignItems: 'baseline', gap: '8px',
          marginBottom: '12px',
        }}>
          <span style={{
            fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)',
          }}>
            {t('session.timeline.title')}
          </span>
          {/* Anti-detección hint — P3: oculto en móvil */}
          <span style={{
            fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 400,
          }}
            className="hidden-mobile"
          >
            · {t('session.timeline.antiDetectionHint')}
          </span>
        </div>

        {timelinesError && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            padding: '24px', gap: '10px', textAlign: 'center',
          }} role="alert">
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              {timelinesError}
            </div>
            <button
              type="button"
              onClick={fetchTimelines}
              style={retryBtnStyle}
            >
              {t('session.status.retry')}
            </button>
          </div>
        )}

        {!timelinesError && (
          <>
            {/* Selector de días */}
            <WeekdaySelector
              timelines={timelines}
              selectedDay={selectedDay}
              onSelect={handleSelectDay}
              loading={timelinesLoading}
              todayWeekday={todayWeekday}
            />

            {/* Barra de timeline del día seleccionado */}
            {selectedTimeline && (
              <div style={{ marginTop: '14px' }}>
                <TimelineBar
                  blocks={editBlocks ?? normalizeBlocks(selectedTimeline.blocks)}
                  dayLabel={selectedDayLabel}
                />
              </div>
            )}

            {/* Placeholder cuando no hay día seleccionado */}
            {selectedDay === null && !timelinesLoading && (
              <div style={{ marginTop: '14px', fontSize: '13px', color: 'var(--text-tertiary)', textAlign: 'center', padding: '16px 0' }}>
                {t('session.editor.noDay')}
              </div>
            )}
          </>
        )}
      </div>

      {/* 4. Editor de bloques (visible al seleccionar un día) */}
      {selectedDay !== null && editBlocks !== null && (
        <div ref={editorRef}>
          <BlockEditor
            blocks={editBlocks}
            isDefault={timelines[selectedDay]?.is_default ?? true}
            dayLabel={selectedDayLabel}
            saving={savingBlocks}
            apiError={blockApiError}
            onChange={setEditBlocks}
            onSave={handleSaveBlocks}
            onCopyToDays={handleCopyToDays}
            copying={copyingDays}
          />
        </div>
      )}

    </div>
  )
}

// ─── Estilos ──────────────────────────────────────────────────────────────────

const cardStyle = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  padding: '16px 20px',
}

const retryBtnStyle = {
  padding: '6px 16px',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface)',
  color: 'var(--text)',
  fontSize: '13px',
  cursor: 'pointer',
  fontFamily: 'inherit',
}
