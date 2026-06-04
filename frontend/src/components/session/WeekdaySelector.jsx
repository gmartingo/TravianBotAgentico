/**
 * WeekdaySelector — Fila de 7 botones de día.
 *
 * Props:
 *  - timelines {Array}         — 7 objetos de timeline (de GET .../timeline)
 *  - selectedDay {number|null} — día seleccionado (0=lun…6=dom)
 *  - onSelect {function}       — fn(weekday: number)
 *  - loading {boolean}
 *  - todayWeekday {number}     — día real actual (0=lun…6=dom)
 *
 * Los nombres de día se localizan con Intl: no hardcodeamos "Lun", "Mar"…
 * Spec §6 (selector de días), §7 (estados), §10 (accesibilidad: tablist/tab).
 */
import { useI18n } from '../../i18n/index.jsx'

// Genera los nombres de día abreviados (3 letras) con Intl
function getDayNames(lang) {
  // Mapeo weekday (0=lun…6=dom) → nombre localizado
  const names = []
  // Referencia: 2024-01-01 fue lunes (weekday=0 en nuestro esquema)
  for (let i = 0; i < 7; i++) {
    // Date: 2024-01-01 = lunes → +i días
    const date = new Date(2024, 0, 1 + i)
    const short = new Intl.DateTimeFormat(lang, { weekday: 'short' }).format(date)
    // Capitalizar primera letra y recortar a 3 chars si hace falta
    const normalized = short.charAt(0).toUpperCase() + short.slice(1)
    names.push(normalized.length > 4 ? normalized.slice(0, 3) : normalized)
  }
  return names
}

function getFirstModeColor(timeline) {
  if (!timeline || !timeline.blocks || timeline.blocks.length === 0) return null
  const mode = timeline.blocks[0].mode?.toLowerCase()
  if (mode === 'hardcore') return 'var(--mode-hardcore)'
  if (mode === 'pasivo') return 'var(--mode-pasivo)'
  return 'var(--mode-disconnected)'
}

function getFirstModeOpacity(timeline) {
  if (!timeline || !timeline.blocks || timeline.blocks.length === 0) return 0.6
  const mode = timeline.blocks[0].mode?.toLowerCase()
  return mode === 'disconnected' ? 0.6 : 1
}

export function WeekdaySelector({ timelines, selectedDay, onSelect, loading, todayWeekday }) {
  const { t, lang } = useI18n()
  const dayNames = getDayNames(lang)

  // Estado cargando: skeletons
  if (loading && (!timelines || timelines.length === 0)) {
    return (
      <div
        role="tablist"
        aria-label={t('session.timeline.title')}
        style={{ display: 'flex', gap: '6px', flexWrap: 'nowrap', overflowX: 'auto', scrollbarWidth: 'none', paddingBottom: '2px' }}
      >
        {Array.from({ length: 7 }).map((_, i) => (
          <div
            key={i}
            style={{
              width: '52px', height: '58px', flexShrink: 0,
              background: 'var(--surface-2)',
              borderRadius: 'var(--radius-sm)',
              animation: 'pulse 1.4s ease-in-out infinite alternate',
            }}
          />
        ))}
      </div>
    )
  }

  return (
    <div
      role="tablist"
      aria-label={t('session.timeline.title')}
      style={{
        display: 'flex', gap: '6px', flexWrap: 'nowrap',
        overflowX: 'auto', scrollbarWidth: 'none',
        paddingBottom: '2px',
      }}
    >
      {dayNames.map((name, i) => {
        const tl = timelines?.[i] ?? null
        const isSelected = selectedDay === i
        const isToday = todayWeekday === i
        const isDefault = tl?.is_default ?? true
        const dotColor = getFirstModeColor(tl)
        const dotOpacity = getFirstModeOpacity(tl)

        return (
          <button
            key={i}
            type="button"
            role="tab"
            aria-selected={isSelected}
            onClick={() => onSelect(i)}
            title={isToday ? t('session.day.today') : name}
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '3px',
              padding: '8px 12px',
              border: isSelected
                ? '1px solid var(--accent)'
                : isToday
                  ? '1px solid var(--text-tertiary)'
                  : '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              background: isSelected ? 'var(--accent-subtle)' : 'var(--surface)',
              color: isSelected ? 'var(--accent-text)' : 'var(--text)',
              fontSize: '13px', fontWeight: 500,
              cursor: 'pointer',
              minWidth: '52px', flexShrink: 0,
              fontFamily: 'inherit',
              transition: 'border-color var(--dur-fast), background var(--dur-fast), color var(--dur-fast)',
              // Targets táctiles ≥44px en móvil
              minHeight: '44px',
            }}
          >
            <span>{name}</span>
            {/* Dot de color del primer modo */}
            {dotColor && (
              <span
                aria-hidden="true"
                style={{
                  width: '6px', height: '6px',
                  borderRadius: '50%',
                  background: dotColor,
                  opacity: dotOpacity,
                  flexShrink: 0,
                }}
              />
            )}
            {/* Etiqueta DEFAULT si is_default */}
            {isDefault && (
              <span style={{
                fontSize: '10px',
                color: 'var(--text-tertiary)',
                fontFamily: 'var(--font-mono)',
                textTransform: 'uppercase',
                letterSpacing: '.04em',
              }}>
                {t('session.timeline.default')}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
