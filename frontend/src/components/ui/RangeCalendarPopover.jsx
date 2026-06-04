/**
 * RangeCalendarPopover — Editor visual de rango de fechas para el filtro del
 * Historial de reportes de ataque.
 *
 * Spec: docs/design/calendario-filtro-historial.md (ready-for-impl)
 * Mockup aprobado: frontend/mockups/calendario-filtro-historial.playground.html
 *
 * NO es un estado paralelo: es un editor visual de los DOS inputs de texto
 * "Desde"/"Hasta" (formato "YYYY-MM-DD HH:MM:SS"). Lo que escribe son esos mismos
 * strings; el contrato del endpoint (from_date/to_date) no cambia.
 *
 * Anti-bug de zona horaria (§8 del spec): NUNCA round-trip con new Date(isoString).
 * "Ahora" y los días con getters LOCALES; formateo manual con padding; el parseo de
 * los strings por split (NO new Date(str)); el Date para navegar meses se construye
 * por componentes (new Date(y, m-1, d) = local seguro).
 *
 * Reutiliza:
 *  - Patrón popover de LangPicker.jsx (panel absolute, doble rAF zoom, click-fuera,
 *    Escape, z-index alto, max-w móvil).
 *  - role="dialog" + useFocusTrap de ui/uiUtils.jsx (patrón DeletePopover.jsx).
 *  - Estilo de los inputs de hora replicado de DateFilterInput (32px, mono, borde rojo).
 *  - Intl.DateTimeFormat(lang, …) para meses/días; semana empieza en LUNES siempre.
 *  - Tokens duales claro/oscuro; cero hex hardcodeado.
 *
 * Props:
 *   fromText   — string actual del input "Desde" ("YYYY-MM-DD HH:MM:SS" o "")
 *   toText     — string actual del input "Hasta"
 *   onChange   — (from_date, to_date) => void  — escribe en los inputs de texto
 *   onApply    — () => void  — dispara el mismo Aplicar del filtro (normaliza a ISO)
 *   onClose    — () => void  — cierra el popover
 *   t          — función de traducción de useI18n()
 *   lang       — código de idioma activo (para Intl)
 *   triggerRef — ref del contenedor de los campos de fecha (anclaje + click-fuera)
 *   focusReturnRef — (opcional) ref del elemento que recupera el foco al cerrar
 *                    (p.ej. el input "Desde"). Si falta, cae a triggerRef.
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { useFocusTrap } from './uiUtils.jsx'

// ── Helpers de fecha NAIVE VERBATIM (sin round-trip UTC, §8 del spec) ────────────
const pad = (n) => String(n).padStart(2, '0')

/** Date local → "YYYY-MM-DD HH:MM:SS" usando getters LOCALES (nunca toISOString). */
function fmtDate(d) {
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  )
}

const PARSE_RE = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/

/** "YYYY-MM-DD HH:MM:SS" → {y,mo,d,h,mi,s} por split (NO new Date(str)). */
function parseStr(s) {
  const m = PARSE_RE.exec((s || '').trim())
  if (!m) return null
  return { y: +m[1], mo: +m[2], d: +m[3], h: +m[4], mi: +m[5], s: +m[6] }
}

/** {y,mo,d,h,mi,s} → "YYYY-MM-DD HH:MM:SS" o "" si null. */
function fmtPart(p) {
  return p
    ? `${p.y}-${pad(p.mo)}-${pad(p.d)} ${pad(p.h)}:${pad(p.mi)}:${pad(p.s)}`
    : ''
}

/** Date local seguro por componentes (constructor = local). */
function dateOnly(y, mo, d) {
  return new Date(y, mo - 1, d)
}

/** Índice de columna con semana = LUNES: (getDay()+6)%7 (lun=0 … dom=6). */
function mondayIndex(dateObj) {
  return (dateObj.getDay() + 6) % 7
}

// ── Comparaciones de {y,mo,d} ────────────────────────────────────────────────
function dayValue(a) {
  return a.y * 10000 + a.mo * 100 + a.d
}
function cmpDay(a, b) {
  if (!a || !b) return 0
  const av = dayValue(a)
  const bv = dayValue(b)
  return av < bv ? -1 : av > bv ? 1 : 0
}
function sameDay(a, b) {
  return a && b && a.y === b.y && a.mo === b.mo && a.d === b.d
}

/** Valor entero ordenable de un instante completo (para detectar from>to). */
function ordValue(p) {
  return p
    ? p.y * 1e10 + p.mo * 1e8 + p.d * 1e6 + p.h * 1e4 + p.mi * 1e2 + p.s
    : null
}

function clampInt(v, min, max, dflt) {
  const s = String(v).trim()
  if (s === '' || isNaN(+s)) return dflt
  return Math.max(min, Math.min(max, parseInt(s, 10)))
}

const RANGE_RADIUS = 'var(--radius-sm)'

export function RangeCalendarPopover({
  fromText,
  toText,
  onChange,
  onApply,
  onClose,
  t,
  lang,
  triggerRef,
  focusReturnRef,
}) {
  const panelRef = useRef(null)

  // Estado del rango: from/to = {y,mo,d,h,mi,s} | null
  const initFrom = parseStr(fromText)
  const initTo = parseStr(toText)
  const [from, setFrom] = useState(initFrom)
  const [to, setTo] = useState(initTo)
  const [awaitingSecond, setAwaitingSecond] = useState(!!(initFrom && !initTo))

  // Strings en bruto de los inputs de hora (para permitir borrar/teclear libremente)
  const [timeStr, setTimeStr] = useState({
    fromH: initFrom ? pad(initFrom.h) : '',
    fromM: initFrom ? pad(initFrom.mi) : '',
    fromS: initFrom ? pad(initFrom.s) : '',
    toH: initTo ? pad(initTo.h) : '',
    toM: initTo ? pad(initTo.mi) : '',
    toS: initTo ? pad(initTo.s) : '',
  })

  // Mes visible (1-12). Inicial: mes de from, si no de to, si no el actual.
  const [view, setView] = useState(() => {
    const base = initFrom || initTo
    if (base) return { y: base.y, mo: base.mo }
    const now = new Date()
    return { y: now.getFullYear(), mo: now.getMonth() + 1 }
  })

  // Animación zoom (doble rAF, patrón LangPicker)
  const [show, setShow] = useState(false)

  // prefers-reduced-motion (desactiva animación del popover y de las filas de hora)
  const reduceMotion = useMemo(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  )

  useFocusTrap(panelRef, true)

  // Zoom-in al montar
  useEffect(() => {
    if (reduceMotion) {
      setShow(true)
      return
    }
    let raf2
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setShow(true))
    })
    return () => {
      cancelAnimationFrame(raf1)
      if (raf2) cancelAnimationFrame(raf2)
    }
  }, [reduceMotion])

  const closeAndFocus = useCallback(() => {
    onClose()
    // Devolver foco al elemento de retorno (input "Desde") o al trigger tras desmontar
    requestAnimationFrame(() =>
      (focusReturnRef?.current ?? triggerRef?.current)?.focus(),
    )
  }, [onClose, triggerRef, focusReturnRef])

  // Escape cierra; clic fuera cierra
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        closeAndFocus()
      }
    }
    function onDocMouseDown(e) {
      if (
        panelRef.current &&
        !panelRef.current.contains(e.target) &&
        !triggerRef?.current?.contains(e.target)
      ) {
        onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDocMouseDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDocMouseDown)
    }
  }, [closeAndFocus, onClose, triggerRef])

  // Si los inputs de texto cambian por fuera (teclear directo), reflejar al calendario.
  useEffect(() => {
    const f = parseStr(fromText)
    const tp = parseStr(toText)
    setFrom(f)
    setTo(tp)
    setAwaitingSecond(!!(f && !tp))
    setTimeStr({
      fromH: f ? pad(f.h) : '',
      fromM: f ? pad(f.mi) : '',
      fromS: f ? pad(f.s) : '',
      toH: tp ? pad(tp.h) : '',
      toM: tp ? pad(tp.mi) : '',
      toS: tp ? pad(tp.s) : '',
    })
    if (f) setView({ y: f.y, mo: f.mo })
    else if (tp) setView({ y: tp.y, mo: tp.mo })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromText, toText])

  // ── Intl: nombres de mes y de día (semana = LUNES) ──────────────────────────
  const monthLabel = useMemo(() => {
    const d = new Date(view.y, view.mo - 1, 1)
    return new Intl.DateTimeFormat(lang, { month: 'long', year: 'numeric' }).format(d)
  }, [view, lang])

  const dayNames = useMemo(() => {
    // 2024-01-01 fue LUNES → 7 etiquetas cortas empezando en lunes
    const base = new Date(2024, 0, 1)
    const fmtD = new Intl.DateTimeFormat(lang, { weekday: 'short' })
    const out = []
    for (let i = 0; i < 7; i++) {
      const d = new Date(base)
      d.setDate(base.getDate() + i)
      out.push(fmtD.format(d))
    }
    return out
  }, [lang])

  const dayAria = useCallback(
    (y, mo, d) =>
      new Intl.DateTimeFormat(lang, {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      }).format(new Date(y, mo - 1, d)),
    [lang],
  )

  // ── Propaga from/to a los inputs de texto del filtro ────────────────────────
  const pushToInputs = useCallback(
    (f, tp) => {
      onChange(fmtPart(f), fmtPart(tp))
    },
    [onChange],
  )

  // ── Selección de día: 1º = from; 2º = to (auto-swap); 3º = reinicio ─────────
  function pickDay(day) {
    let nf
    let nt
    if (!from || (from && to)) {
      // primer extremo (o reinicio tras rango completo): conserva hora ya tecleada
      nf = {
        ...day,
        h: clampInt(timeStr.fromH, 0, 23, 0),
        mi: clampInt(timeStr.fromM, 0, 59, 0),
        s: clampInt(timeStr.fromS, 0, 59, 0),
      }
      nt = null
      setAwaitingSecond(true)
    } else {
      // segundo extremo
      let f = { ...from }
      let tp = { ...day }
      if (cmpDay(tp, f) < 0) {
        // auto-swap: el día anterior pasa a ser from, el viejo from pasa a ser to
        const oldFrom = f
        f = { ...tp, h: oldFrom.h, mi: oldFrom.mi, s: oldFrom.s }
        tp = { ...oldFrom }
      }
      // horas: from conserva su input; to toma su input o 23:59:59 si vacío
      f.h = clampInt(timeStr.fromH, 0, 23, 0)
      f.mi = clampInt(timeStr.fromM, 0, 59, 0)
      f.s = clampInt(timeStr.fromS, 0, 59, 0)
      const hasToTime = timeStr.toH || timeStr.toM || timeStr.toS
      tp.h = clampInt(timeStr.toH, 0, 23, hasToTime ? 0 : 23)
      tp.mi = clampInt(timeStr.toM, 0, 59, hasToTime ? 0 : 59)
      tp.s = clampInt(timeStr.toS, 0, 59, hasToTime ? 0 : 59)
      nf = f
      nt = tp
      setAwaitingSecond(false)
    }
    setFrom(nf)
    setTo(nt)
    setTimeStr({
      fromH: nf ? pad(nf.h) : '',
      fromM: nf ? pad(nf.mi) : '',
      fromS: nf ? pad(nf.s) : '',
      toH: nt ? pad(nt.h) : '',
      toM: nt ? pad(nt.mi) : '',
      toS: nt ? pad(nt.s) : '',
    })
    pushToInputs(nf, nt)
  }

  // ── Atajos: calculan "ahora" en LOCAL, sin UTC (§6 / §8) ────────────────────
  function applyShortcut(kind) {
    const now = new Date()
    let f
    if (kind === 'hour') {
      f = new Date(now.getTime() - 3600 * 1000)
    } else if (kind === 'day') {
      f = new Date(now.getTime() - 86400 * 1000)
    } else {
      // monday: lunes de esta semana a las 00:00:00
      const back = (now.getDay() + 6) % 7
      f = new Date(now.getFullYear(), now.getMonth(), now.getDate() - back, 0, 0, 0)
    }
    const nf = {
      y: f.getFullYear(),
      mo: f.getMonth() + 1,
      d: f.getDate(),
      h: f.getHours(),
      mi: f.getMinutes(),
      s: f.getSeconds(),
    }
    const nt = {
      y: now.getFullYear(),
      mo: now.getMonth() + 1,
      d: now.getDate(),
      h: now.getHours(),
      mi: now.getMinutes(),
      s: now.getSeconds(),
    }
    setFrom(nf)
    setTo(nt)
    setAwaitingSecond(false)
    setView({ y: nf.y, mo: nf.mo })
    setTimeStr({
      fromH: pad(nf.h),
      fromM: pad(nf.mi),
      fromS: pad(nf.s),
      toH: pad(nt.h),
      toM: pad(nt.mi),
      toS: pad(nt.s),
    })
    pushToInputs(nf, nt)
  }

  // ── Edición de hora: onChange acumula dígitos; onBlur zero-pad + clamp ──────
  function handleTimeChange(field, value) {
    const digits = value.replace(/\D/g, '').slice(0, 2)
    setTimeStr((prev) => ({ ...prev, [field]: digits }))
  }

  function handleTimeBlur(field) {
    setTimeStr((prev) => {
      const max = field.endsWith('H') ? 23 : 59
      const raw = prev[field]
      const padded = raw === '' ? '' : pad(clampInt(raw, 0, max, 0))
      const next = { ...prev, [field]: padded }
      // reflejar en estado + inputs de texto
      const isFrom = field.startsWith('from')
      if (isFrom && from) {
        const nf = {
          ...from,
          h: clampInt(next.fromH, 0, 23, from.h),
          mi: clampInt(next.fromM, 0, 59, from.mi),
          s: clampInt(next.fromS, 0, 59, from.s),
        }
        setFrom(nf)
        pushToInputs(nf, to)
      } else if (!isFrom && to) {
        const nt = {
          ...to,
          h: clampInt(next.toH, 0, 23, to.h),
          mi: clampInt(next.toM, 0, 59, to.mi),
          s: clampInt(next.toS, 0, 59, to.s),
        }
        setTo(nt)
        pushToInputs(from, nt)
      }
      return next
    })
  }

  // ── Limpiar (dentro del popover): vacía rango, re-oculta horas, no cierra ───
  function handleClear() {
    setFrom(null)
    setTo(null)
    setAwaitingSecond(false)
    setTimeStr({ fromH: '', fromM: '', fromS: '', toH: '', toM: '', toS: '' })
    pushToInputs(null, null)
  }

  // ── Validación de orden (deshabilita Aplicar) ───────────────────────────────
  const orderError =
    from && to && ordValue(from) > ordValue(to)

  function handleApplyRange() {
    if (orderError) return
    onApply()
    closeAndFocus()
  }

  // Navegación de mes
  function prevMonth() {
    setView((v) => {
      let mo = v.mo - 1
      let y = v.y
      if (mo < 1) {
        mo = 12
        y -= 1
      }
      return { y, mo }
    })
  }
  function nextMonth() {
    setView((v) => {
      let mo = v.mo + 1
      let y = v.y
      if (mo > 12) {
        mo = 1
        y += 1
      }
      return { y, mo }
    })
  }

  // ── Construir las celdas del grid ───────────────────────────────────────────
  const today = useMemo(() => {
    const n = new Date()
    return { y: n.getFullYear(), mo: n.getMonth() + 1, d: n.getDate() }
  }, [])

  const cells = useMemo(() => {
    const first = dateOnly(view.y, view.mo, 1)
    const offset = mondayIndex(first)
    const daysInMonth = new Date(view.y, view.mo, 0).getDate()
    const out = []
    for (let i = 0; i < offset; i++) out.push({ blank: true, key: `b${i}` })
    for (let d = 1; d <= daysInMonth; d++) {
      out.push({ blank: false, key: `d${d}`, day: { y: view.y, mo: view.mo, d } })
    }
    return out
  }, [view])

  // Día con tabindex=0 (roving): from, si no to, si no hoy si está en el mes, si no día 1
  const rovingDay = useMemo(() => {
    if (from && from.y === view.y && from.mo === view.mo) return from.d
    if (to && to.y === view.y && to.mo === view.mo) return to.d
    if (today.y === view.y && today.mo === view.mo) return today.d
    return 1
  }, [from, to, today, view])

  // ── Navegación por teclado dentro del grid ──────────────────────────────────
  function handleGridKeyDown(e, day) {
    const { key } = e
    let nd = day.d
    const daysInMonth = new Date(view.y, view.mo, 0).getDate()
    if (key === 'ArrowLeft') nd = day.d - 1
    else if (key === 'ArrowRight') nd = day.d + 1
    else if (key === 'ArrowUp') nd = day.d - 7
    else if (key === 'ArrowDown') nd = day.d + 7
    else if (key === 'Home') nd = day.d - mondayIndex(dateOnly(view.y, view.mo, day.d))
    else if (key === 'End')
      nd = day.d + (6 - mondayIndex(dateOnly(view.y, view.mo, day.d)))
    else if (key === 'PageUp') {
      e.preventDefault()
      prevMonth()
      return
    } else if (key === 'PageDown') {
      e.preventDefault()
      nextMonth()
      return
    } else if (key === 'Enter' || key === ' ') {
      e.preventDefault()
      pickDay(day)
      return
    } else {
      return
    }
    e.preventDefault()
    // cambio de mes si nos salimos
    if (nd < 1) {
      prevMonth()
      return
    }
    if (nd > daysInMonth) {
      nextMonth()
      return
    }
    // mover foco a la celda destino
    const grid = panelRef.current?.querySelector('[data-cal-grid]')
    const target = grid?.querySelector(`[data-day="${nd}"]`)
    target?.focus()
  }

  const showFromTime = !!from
  const showToTime = !!to
  const sectionVisible = showFromTime || showToTime

  // Estilos base inline (tokens, cero hex)
  const sectionStyle = {
    padding: '12px 14px',
    borderBottom: '1px solid var(--border)',
  }
  const secLabelStyle = {
    fontSize: '11px',
    color: 'var(--text-tertiary)',
    fontWeight: 500,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
    marginBottom: '8px',
  }

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-label={t('ar.history.filter.cal.title')}
      className="
        absolute end-0 top-[calc(100%+8px)] w-[330px]
        max-w-[calc(100vw-32px)]
        bg-[var(--surface)] border border-[var(--border)]
        rounded-[var(--radius-md)] shadow-[var(--shadow-lg)]
        overflow-hidden z-[300]
      "
      style={{
        transformOrigin: 'top center',
        transition: reduceMotion
          ? 'none'
          : 'transform 150ms cubic-bezier(0.16,1,0.3,1), opacity 150ms ease-out',
        transform: show ? 'scale(1)' : 'scale(0.95)',
        opacity: show ? 1 : 0,
      }}
    >
      {/* Cabecera */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 14px',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text)' }}>
          {t('ar.history.filter.cal.title')}
        </h3>
        <button
          type="button"
          onClick={closeAndFocus}
          aria-label={t('ar.history.filter.cal.close')}
          style={{
            width: '28px',
            height: '28px',
            display: 'grid',
            placeItems: 'center',
            borderRadius: 'var(--radius-sm)',
            background: 'transparent',
            border: 'none',
            color: 'var(--text-tertiary)',
            cursor: 'pointer',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'var(--surface-2)'
            e.currentTarget.style.color = 'var(--text)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent'
            e.currentTarget.style.color = 'var(--text-tertiary)'
          }}
        >
          <X size={16} aria-hidden="true" />
        </button>
      </div>

      {/* Atajos */}
      <div style={sectionStyle}>
        <div style={secLabelStyle}>{t('ar.history.filter.cal.shortcuts')}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {[
            ['hour', 'ar.history.filter.cal.lastHour'],
            ['day', 'ar.history.filter.cal.lastDay'],
            ['monday', 'ar.history.filter.cal.sinceMonday'],
          ].map(([kind, key]) => (
            <ShortcutButton key={kind} onClick={() => applyShortcut(kind)}>
              {t(key)}
            </ShortcutButton>
          ))}
        </div>
      </div>

      {/* Calendario */}
      <div style={sectionStyle}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '8px',
          }}
        >
          <NavButton onClick={prevMonth} label={t('ar.history.filter.cal.prevMonth')}>
            <ChevronLeft size={14} aria-hidden="true" />
          </NavButton>
          <span
            style={{
              fontSize: '14px',
              fontWeight: 600,
              textTransform: 'capitalize',
              color: 'var(--text)',
            }}
          >
            {monthLabel}
          </span>
          <NavButton onClick={nextMonth} label={t('ar.history.filter.cal.nextMonth')}>
            <ChevronRight size={14} aria-hidden="true" />
          </NavButton>
        </div>

        <div
          data-cal-grid
          role="grid"
          aria-label={`${t('ar.history.filter.cal.gridLabel')}, ${monthLabel}`}
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(7, 1fr)',
            gap: '2px',
          }}
        >
          {dayNames.map((n, i) => (
            <div
              key={`dow${i}`}
              role="columnheader"
              style={{
                textAlign: 'center',
                fontSize: '11px',
                color: 'var(--text-tertiary)',
                fontWeight: 500,
                textTransform: 'capitalize',
                padding: '4px 0',
              }}
            >
              {n}
            </div>
          ))}
          {cells.map((c) => {
            if (c.blank) {
              return (
                <div key={c.key} aria-hidden="true" style={{ aspectRatio: '1 / 1' }} />
              )
            }
            const { day } = c
            const isToday = sameDay(day, today)
            const isFrom = from && sameDay(day, from)
            const isTo = to && sameDay(day, to)
            const isSingle = isFrom && (!to || sameDay(from, to))
            const isInRange =
              from && to && cmpDay(day, from) > 0 && cmpDay(day, to) < 0
            const selected = isFrom || isTo || isInRange
            return (
              <DayCell
                key={c.key}
                day={day}
                label={dayAria(day.y, day.mo, day.d)}
                isToday={isToday}
                isFrom={!!isFrom && !isSingle}
                isTo={!!isTo && !isSingle}
                isSingle={!!isSingle}
                isInRange={!!isInRange}
                selected={!!selected}
                roving={day.d === rovingDay}
                onPick={() => pickDay(day)}
                onKeyDown={(e) => handleGridKeyDown(e, day)}
              />
            )
          })}
        </div>

        <div
          style={{
            fontSize: '12px',
            color: 'var(--text-secondary)',
            marginTop: '8px',
            minHeight: '16px',
          }}
        >
          {awaitingSecond ? t('ar.history.filter.cal.pickEnd') : ''}
        </div>
      </div>

      {/* Sección de hora — revelada progresivamente */}
      <div
        style={{
          overflow: 'hidden',
          maxHeight: sectionVisible ? '160px' : '0',
          paddingTop: sectionVisible ? '12px' : '0',
          paddingBottom: sectionVisible ? '12px' : '0',
          paddingInline: '14px',
          borderBottom: sectionVisible ? '1px solid var(--border)' : 'none',
          opacity: sectionVisible ? 1 : 0,
          transition: reduceMotion
            ? 'none'
            : 'max-height var(--dur-base) var(--ease), padding var(--dur-base) var(--ease), opacity var(--dur-fast) var(--ease)',
        }}
        aria-hidden={sectionVisible ? 'false' : 'true'}
      >
        <div style={secLabelStyle}>{t('ar.history.filter.cal.time')}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '14px' }}>
          <TimeGroup
            visible={showFromTime}
            reduceMotion={reduceMotion}
            label={t('ar.history.filter.from')}
            prefix="from"
            timeStr={timeStr}
            onChange={handleTimeChange}
            onBlur={handleTimeBlur}
            t={t}
          />
          <TimeGroup
            visible={showToTime}
            reduceMotion={reduceMotion}
            label={t('ar.history.filter.to')}
            prefix="to"
            timeStr={timeStr}
            onChange={handleTimeChange}
            onBlur={handleTimeBlur}
            t={t}
          />
        </div>
      </div>

      {/* Error de orden */}
      {orderError && (
        <div
          role="alert"
          style={{
            fontSize: '12px',
            color: 'var(--danger)',
            padding: '0 14px 12px',
          }}
        >
          {t('ar.history.filter.cal.orderError')}
        </div>
      )}

      {/* Acciones */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: '8px',
          padding: '12px 14px',
        }}
      >
        <button
          type="button"
          onClick={handleClear}
          style={{
            height: '32px',
            padding: '0 12px',
            background: 'transparent',
            color: 'var(--text-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
            fontFamily: 'inherit',
            cursor: 'pointer',
          }}
        >
          {t('ar.history.filter.clear')}
        </button>
        <button
          type="button"
          onClick={handleApplyRange}
          disabled={orderError}
          aria-disabled={orderError}
          style={{
            height: '32px',
            padding: '0 14px',
            background: orderError ? 'var(--text-disabled)' : 'var(--btn-primary-bg)',
            color: 'var(--btn-primary-text)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
            fontWeight: 500,
            fontFamily: 'inherit',
            cursor: orderError ? 'not-allowed' : 'pointer',
            opacity: orderError ? 0.5 : 1,
          }}
        >
          {t('ar.history.filter.cal.applyRange')}
        </button>
      </div>
    </div>
  )
}

// ── Subcomponentes ────────────────────────────────────────────────────────────

function ShortcutButton({ onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        height: '30px',
        padding: '0 12px',
        background: 'transparent',
        color: 'var(--text)',
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '12px',
        fontFamily: 'inherit',
        cursor: 'pointer',
        whiteSpace: 'nowrap',
        transition:
          'background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'var(--accent-subtle)'
        e.currentTarget.style.borderColor = 'var(--accent)'
        e.currentTarget.style.color = 'var(--accent-text)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'transparent'
        e.currentTarget.style.borderColor = 'var(--border-strong)'
        e.currentTarget.style.color = 'var(--text)'
      }}
    >
      {children}
    </button>
  )
}

function NavButton({ onClick, label, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      style={{
        width: '28px',
        height: '28px',
        display: 'grid',
        placeItems: 'center',
        borderRadius: 'var(--radius-sm)',
        background: 'transparent',
        border: '1px solid var(--border)',
        color: 'var(--text-secondary)',
        cursor: 'pointer',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'var(--surface-2)'
        e.currentTarget.style.borderColor = 'var(--accent)'
        e.currentTarget.style.color = 'var(--accent-text)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'transparent'
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.color = 'var(--text-secondary)'
      }}
    >
      {children}
    </button>
  )
}

function DayCell({
  day,
  label,
  isToday,
  isFrom,
  isTo,
  isSingle,
  isInRange,
  selected,
  roving,
  onPick,
  onKeyDown,
}) {
  const isEnd = isFrom || isTo || isSingle
  const base = {
    aspectRatio: '1 / 1',
    minHeight: '32px',
    display: 'grid',
    placeItems: 'center',
    border: 'none',
    background: 'transparent',
    color: 'var(--text)',
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
    fontVariantNumeric: 'tabular-nums',
    fontSize: '13px',
    borderRadius: 'var(--radius-sm)',
    transition: 'background var(--dur-fast)',
    position: 'relative',
    fontWeight: isToday ? 700 : 400,
  }

  if (isInRange) {
    base.background = 'var(--accent-subtle)'
    base.borderRadius = '0'
  }
  if (isSingle) {
    base.background = 'var(--accent)'
    base.color = 'var(--btn-primary-text)'
    base.borderRadius = 'var(--radius-sm)'
  } else if (isFrom) {
    base.background = 'var(--accent)'
    base.color = 'var(--btn-primary-text)'
    base.borderStartStartRadius = RANGE_RADIUS
    base.borderEndStartRadius = RANGE_RADIUS
    base.borderStartEndRadius = '0'
    base.borderEndEndRadius = '0'
  } else if (isTo) {
    base.background = 'var(--accent)'
    base.color = 'var(--btn-primary-text)'
    base.borderStartEndRadius = RANGE_RADIUS
    base.borderEndEndRadius = RANGE_RADIUS
    base.borderStartStartRadius = '0'
    base.borderEndStartRadius = '0'
  }

  return (
    <button
      type="button"
      data-day={day.d}
      role="gridcell"
      aria-label={label}
      aria-selected={selected ? 'true' : undefined}
      aria-current={isToday ? 'date' : undefined}
      tabIndex={roving ? 0 : -1}
      onClick={onPick}
      onKeyDown={onKeyDown}
      style={base}
      onMouseEnter={(e) => {
        if (!isEnd && !isInRange) e.currentTarget.style.background = 'var(--surface-2)'
      }}
      onMouseLeave={(e) => {
        if (!isEnd && !isInRange) e.currentTarget.style.background = 'transparent'
        else if (isInRange) e.currentTarget.style.background = 'var(--accent-subtle)'
      }}
    >
      {day.d}
      {isToday && (
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            insetBlockEnd: '4px',
            insetInline: 0,
            marginInline: 'auto',
            width: '4px',
            height: '4px',
            borderRadius: '50%',
            background: isEnd ? 'var(--btn-primary-text)' : 'var(--accent)',
          }}
        />
      )}
    </button>
  )
}

function TimeGroup({ visible, reduceMotion, label, prefix, timeStr, onChange, onBlur, t }) {
  const fields = [
    [`${prefix}H`, t('ar.history.filter.cal.hours')],
    [`${prefix}M`, t('ar.history.filter.cal.minutes')],
    [`${prefix}S`, t('ar.history.filter.cal.seconds')],
  ]
  return (
    <div
      hidden={!visible}
      style={{
        display: visible ? 'flex' : 'none',
        flexDirection: 'column',
        gap: '4px',
        opacity: visible ? 1 : 0,
        transform: visible ? 'none' : 'translateY(-2px)',
        transition: reduceMotion
          ? 'none'
          : 'opacity var(--dur-fast) var(--ease), transform var(--dur-fast) var(--ease)',
      }}
    >
      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
        {fields.map(([field, ariaSuffix], idx) => (
          <span key={field} style={{ display: 'inline-flex', alignItems: 'center', gap: '2px' }}>
            {idx > 0 && (
              <span
                aria-hidden="true"
                style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}
              >
                :
              </span>
            )}
            <input
              type="text"
              inputMode="numeric"
              maxLength={2}
              value={timeStr[field]}
              aria-label={`${label} ${ariaSuffix}`}
              placeholder="00"
              onChange={(e) => onChange(field, e.target.value)}
              onBlur={() => onBlur(field)}
              style={{
                width: '34px',
                height: '32px',
                textAlign: 'center',
                background: 'var(--surface)',
                border: '1px solid var(--border-strong)',
                borderRadius: 'var(--radius-sm)',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
                color: 'var(--text)',
                outline: 'none',
                boxSizing: 'border-box',
              }}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = 'var(--accent)'
              }}
              onBlurCapture={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-strong)'
              }}
            />
          </span>
        ))}
      </div>
    </div>
  )
}
