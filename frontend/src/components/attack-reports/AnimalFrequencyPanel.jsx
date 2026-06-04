/**
 * AnimalFrequencyPanel — Cadencia de farmeo y animales esperados (v5).
 *
 * Spec: docs/design/animal-frequency-panel.md (v5, ready-for-impl)
 * Consume: GET /attack-reports/stats/oasis/temporal-distribution?interval_minutes=N
 * Método cliente: api.getAnimalTemporalDistribution(intervalMinutes)
 *
 * Estructura:
 *   1. FrequencySelector — dos grupos de pills (minutos / horas), default 240
 *   2. TypeTabSelector   — 5 pestañas (hierro / barro / madera / cereal / sin_clasificar)
 *   3. TypeSummaryCard   — ficha de resumen del tipo activo (total animales, botín, coords)
 *   4. AnimalList        — lista de animales del tipo activo (icono + media + moda + peor)
 *
 * Todos los estados del spec §7:
 *   loading, error, vacío global, vacío de frecuencia, tipo vacío, con datos,
 *   animal con avg null, pestaña Sin clasificar, pestaña Cereal, pestaña sin datos.
 *
 * Patrón "dumb component":
 *   AnimalFrequencyPanel recibe: data, loading, error, intervalMinutes,
 *   onIntervalChange, onRetry, onGoToIngest, lang, t.
 *   Gestiona internamente: activeType (pestaña activa).
 *
 * Accesibilidad: role="tablist/tab/tabpanel", navegación flechas, aria-pressed en pills,
 *   role="status" en skeleton, role="alert" en error, foco visible en todos los controles.
 *
 * Responsive: FrequencySelector en dos filas <md, TypeTabSelector con scroll horizontal,
 *   cifra protagonista 20px en móvil vs 22px en desktop.
 *
 * i18n: claves ar.freq.* en catálogo. Propiedades CSS lógicas para RTL.
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { NatureIcon } from './NatureIcon.jsx'
import { ResIcon } from '../combat/TravianReport.jsx'
import { formatCoord } from '../../utils/coordUtils.js'

// ── Normalización del contrato del backend ────────────────────────────────────
/**
 * El backend devuelve types[] como array con oasis_type como clave.
 * El backend usa "arcilla" para lo que el spec diseño llama "barro".
 * El backend usa "animal_ordinal" en vez de "ordinal".
 *
 * normalizeResponse convierte:
 *   { types: [{oasis_type: "hierro", ...}, {oasis_type: "arcilla", ...}] }
 * a:
 *   { types: { hierro: {...}, barro: {...}, ... }, is_empty_db: bool }
 *
 * También normaliza los animales: animal_ordinal → ordinal para NatureIcon.
 */
function normalizeResponse(raw) {
  if (!raw) return null

  const typesArray = Array.isArray(raw.types) ? raw.types : []

  // Mapeo clave backend → clave interna del spec de diseño
  const TYPE_KEY_MAP = {
    hierro: 'hierro',
    arcilla: 'barro',   // backend usa "arcilla", diseño usa "barro"
    barro: 'barro',     // por si alguna versión usa "barro"
    madera: 'madera',
    cereal: 'cereal',
    sin_clasificar: 'sin_clasificar',
  }

  const typesObj = {}
  for (const typeSection of typesArray) {
    const backendKey = typeSection.oasis_type
    const designKey = TYPE_KEY_MAP[backendKey] ?? backendKey

    // Normalizar animales: animal_ordinal → ordinal
    const animals = (typeSection.animals ?? []).map(a => ({
      ...a,
      ordinal: a.ordinal ?? a.animal_ordinal ?? null,
    }))

    typesObj[designKey] = { ...typeSection, animals }
  }

  // is_empty_db: BD completamente vacía (todos los tipos con 0 reportes y 0 oasis)
  const is_empty_db = typesArray.every(t => (t.n_reports_in_section ?? 0) === 0 && (t.n_oasis ?? 0) === 0)

  return { ...raw, types: typesObj, is_empty_db }
}

// ── Constantes ────────────────────────────────────────────────────────────────

// Orden fijo de los 5 tipos de oasis (spec §7.5)
const TYPE_ORDER = ['hierro', 'barro', 'madera', 'cereal', 'sin_clasificar']

// Opciones del FrequencySelector (spec §8.2 + §6A)
const FREQ_MINUTES = [6, 7, 10, 15, 30]
const FREQ_HOURS = [60, 120, 180, 240, 300] // 1h, 2h, 3h, 4h, 5h+

// Label de cada opción (no localizado — las etiquetas son cortas y autoexplicativas)
function freqLabel(min) {
  if (min < 60) return `${min} min`
  if (min === 300) return '5h+'
  return `${min / 60}h`
}

// ── Sub-componente: FrequencySelector ────────────────────────────────────────
/**
 * Selector de cadencia. Dos grupos de pills (minutos / horas).
 * En desktop: una fila con divisor vertical entre grupos.
 * En móvil: dos filas sin divisor.
 */
function FrequencySelector({ value, onChange, disabled, t }) {
  const handleKey = useCallback((e, opt) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      if (!disabled) onChange(opt)
    }
  }, [disabled, onChange])

  const pillStyle = (isActive) => ({
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '4px 12px',
    borderRadius: 'var(--radius-full)',
    fontSize: '13px',
    fontWeight: isActive ? 600 : 500,
    fontFamily: 'var(--font-mono)',
    fontVariantNumeric: 'tabular-nums',
    cursor: disabled ? 'not-allowed' : 'pointer',
    border: isActive ? '1px solid var(--accent)' : '1px solid var(--border-strong)',
    background: isActive ? 'var(--accent-subtle)' : 'var(--surface-2)',
    color: isActive ? 'var(--accent-text)' : 'var(--text)',
    transition: 'background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast)',
    opacity: disabled ? 0.4 : 1,
    outline: 'none',
    minHeight: '32px',
    whiteSpace: 'nowrap',
  })

  function Pill({ opt }) {
    const isActive = opt === value
    return (
      <button
        type="button"
        role="button"
        aria-pressed={isActive}
        aria-disabled={disabled || undefined}
        disabled={disabled}
        onClick={() => !disabled && onChange(opt)}
        onKeyDown={(e) => handleKey(e, opt)}
        style={pillStyle(isActive)}
        onFocus={(e) => { e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '2px' }}
        onBlur={(e) => { e.currentTarget.style.outline = ''; e.currentTarget.style.outlineOffset = '' }}
        onMouseEnter={(e) => { if (!disabled && !isActive) e.currentTarget.style.borderColor = 'var(--accent)' }}
        onMouseLeave={(e) => { if (!disabled && !isActive) e.currentTarget.style.borderColor = 'var(--border-strong)' }}
      >
        {freqLabel(opt)}
      </button>
    )
  }

  return (
    <div
      role="group"
      aria-label={t('ar.freq.selector_label')}
      style={{ marginBlockEnd: '24px' }}
    >
      <span
        style={{
          display: 'block',
          fontSize: '12px',
          color: 'var(--text-secondary)',
          fontWeight: 500,
          marginBlockEnd: '8px',
        }}
      >
        {t('ar.freq.selector_label')}
      </span>
      {/* Desktop: fila única con divisor. Móvil: dos filas */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        {/* Grupo minutos */}
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {FREQ_MINUTES.map((opt) => <Pill key={opt} opt={opt} />)}
        </div>
        {/* Divisor — visible en md+ */}
        <span
          aria-hidden="true"
          style={{
            display: 'inline-block',
            width: '1px',
            height: '20px',
            background: 'var(--border)',
            alignSelf: 'center',
            flexShrink: 0,
          }}
        />
        {/* Grupo horas */}
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {FREQ_HOURS.map((opt) => <Pill key={opt} opt={opt} />)}
        </div>
      </div>
    </div>
  )
}

// ── Sub-componente: TypeTabSelector ──────────────────────────────────────────
/**
 * Tab bar de 5 pestañas de tipo de oasis (spec §8.2).
 * role="tablist" + role="tab". Navegación por flechas izquierda/derecha.
 */
function TypeTabSelector({ types, activeType, onTypeChange, t }) {
  const tabRefs = useRef([])

  function handleKeyDown(e, idx) {
    const count = TYPE_ORDER.length
    let next = null
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      next = (idx + 1) % count
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      next = (idx - 1 + count) % count
    } else if (e.key === 'Home') {
      e.preventDefault()
      next = 0
    } else if (e.key === 'End') {
      e.preventDefault()
      next = count - 1
    }
    if (next !== null) {
      tabRefs.current[next]?.focus()
    }
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      const typeKey = TYPE_ORDER[idx]
      const typeData = types?.[typeKey]
      onTypeChange(typeKey, typeData)
    }
  }

  const typeLabel = (key) => {
    const labels = {
      hierro: t('ar.freq.type.hierro'),
      barro: t('ar.freq.type.barro'),
      madera: t('ar.freq.type.madera'),
      cereal: t('ar.freq.type.cereal'),
      sin_clasificar: t('ar.freq.type.sin_clasificar'),
    }
    return labels[key] ?? key
  }

  return (
    <div style={{ overflowX: 'auto', scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch' }}>
      <div
        role="tablist"
        aria-label={t('ar.freq.tablist_label')}
        style={{
          display: 'flex',
          gap: '0',
          borderBottom: '1px solid var(--border)',
          minWidth: 'max-content',
        }}
      >
        {TYPE_ORDER.map((key, idx) => {
          const typeData = types?.[key]
          const hasData = typeData && (typeData.n_reports_in_section ?? 0) > 0
          const isActive = key === activeType
          const count = typeData?.n_reports_in_section ?? 0

          return (
            <button
              key={key}
              id={`tab-freq-${key}`}
              role="tab"
              aria-selected={isActive}
              aria-controls={`panel-freq-${key}`}
              aria-disabled={!hasData || undefined}
              ref={(el) => { tabRefs.current[idx] = el }}
              tabIndex={isActive ? 0 : -1}
              onClick={() => onTypeChange(key, typeData)}
              onKeyDown={(e) => handleKeyDown(e, idx)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 16px',
                paddingBlockEnd: '10px',
                fontSize: '13px',
                fontWeight: isActive ? 600 : 500,
                color: isActive
                  ? 'var(--accent-text)'
                  : !hasData
                    ? 'var(--text-disabled)'
                    : 'var(--text-secondary)',
                background: 'transparent',
                border: 'none',
                borderBottom: isActive
                  ? '2px solid var(--accent)'
                  : '2px solid transparent',
                marginBlockEnd: '-1px',
                cursor: 'pointer',
                transition: 'color var(--dur-fast)',
                outline: 'none',
                whiteSpace: 'nowrap',
                flexShrink: 0,
              }}
              onFocus={(e) => { e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '2px' }}
              onBlur={(e) => { e.currentTarget.style.outline = ''; e.currentTarget.style.outlineOffset = '' }}
            >
              <span>{typeLabel(key)}</span>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontVariantNumeric: 'tabular-nums',
                  fontSize: '12px',
                  color: isActive
                    ? 'var(--accent-text)'
                    : !hasData
                      ? 'var(--text-disabled)'
                      : 'var(--text-tertiary)',
                  opacity: isActive ? 0.85 : 1,
                }}
              >
                {hasData ? count : '—'}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ── Sub-componente: TypeSummaryCard ──────────────────────────────────────────
/**
 * Ficha de resumen del tipo activo: total animales, botín, coords.
 * Sin borde ni fondo propios. Solo hairline inferior antes de la lista (spec §14).
 */
function TypeSummaryCard({ typeData, typeName, intervalLabel, lang, t }) {
  if (!typeData || (typeData.n_reports_in_section ?? 0) === 0) return null

  const {
    total_animals,
    avg_bounty,
    n_oasis,
    n_oasis_low_confidence,
    oasis_coords,
    n_reports_in_section,
  } = typeData

  // ── Línea de contexto
  const contextLine = t('ar.freq.section_heading', { type: typeName, label: intervalLabel })

  // ── Línea de confianza
  let confidenceLine
  const badCoords = n_oasis_low_confidence ?? 0
  if (badCoords > 0 && badCoords < (n_oasis ?? 1)) {
    confidenceLine = t('ar.freq.confidence_low_partial', {
      bad: badCoords,
      total: n_oasis ?? '?',
      n: n_reports_in_section ?? 0,
    })
  } else if (badCoords > 0) {
    confidenceLine = t('ar.freq.confidence_low_all', { n: n_reports_in_section ?? 0 })
  } else {
    confidenceLine = t('ar.freq.confidence_base', {
      n: n_reports_in_section ?? 0,
      oasis: n_oasis ?? 0,
    })
  }
  const isLowConfidence = badCoords > 0

  // ── Chips de coordenadas
  const coords = Array.isArray(oasis_coords) ? oasis_coords : []
  const MAX_CHIPS = 3
  const visibleCoords = coords.slice(0, MAX_CHIPS)
  const extraCount = coords.length - MAX_CHIPS

  // ── Total de animales
  const ta = total_animals ?? {}
  const taAvg = ta.avg ?? null
  const taMode = Array.isArray(ta.mode) ? ta.mode : []
  const taMax = ta.max ?? null

  // Formato de la moda (posible empate)
  let modeStr = null
  if (taMode.length >= 2) {
    modeStr = t('ar.freq.mode_tie', { a: taMode[0], b: taMode[1] })
  } else if (taMode.length === 1) {
    modeStr = `${taMode[0]}`
  }

  // ── Botín medio
  const bounty = avg_bounty ?? {}
  const allZero = !bounty.wood && !bounty.clay && !bounty.iron && !bounty.crop && !bounty.total
  const RES_KEYS = ['wood', 'clay', 'iron', 'crop']

  return (
    <div
      style={{
        paddingBlock: '16px',
        borderBottom: '1px solid var(--border)',
        marginBlockEnd: '0',
      }}
    >
      {/* Línea de contexto */}
      <p
        style={{
          fontSize: '14px',
          fontWeight: 500,
          color: 'var(--text)',
          marginBlockEnd: '4px',
        }}
      >
        {contextLine}
      </p>

      {/* Línea de confianza + chips de coords */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          flexWrap: 'wrap',
          gap: '4px',
          marginBlockEnd: '12px',
        }}
      >
        <span
          style={{
            fontSize: '12px',
            color: isLowConfidence ? 'var(--accent-text)' : 'var(--text-tertiary)',
          }}
        >
          · {confidenceLine}
        </span>
        {/* Punto de confianza baja */}
        {isLowConfidence && (
          <span
            aria-hidden="true"
            style={{
              display: 'inline-block',
              width: '5px',
              height: '5px',
              borderRadius: '50%',
              background: 'var(--accent)',
              alignSelf: 'center',
              marginInlineStart: '2px',
              flexShrink: 0,
            }}
          />
        )}
        {/* Chips de coordenadas */}
        {visibleCoords.map((c, i) => (
          <span
            key={i}
            aria-label={formatCoord(c.x, c.y)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-full)',
              padding: '1px 6px',
              fontFamily: 'var(--font-mono)',
              fontVariantNumeric: 'tabular-nums',
              fontSize: '11px',
              color: 'var(--text-secondary)',
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            {formatCoord(c.x, c.y)}
          </span>
        ))}
        {extraCount > 0 && (
          <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
            {t('ar.freq.summary_coords_more', { n: extraCount })}
          </span>
        )}
      </div>

      {/* Total de animales */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          flexWrap: 'wrap',
          gap: '6px',
          marginBlockEnd: '8px',
        }}
      >
        <span style={{ fontSize: '12px', color: 'var(--text-secondary)', flexShrink: 0 }}>
          {t('ar.freq.summary_total_label')}
        </span>
        {taAvg == null ? (
          <span style={{ fontSize: '17px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-disabled)' }}>—</span>
        ) : (
          <>
            <span
              style={{
                fontSize: '17px',
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                fontVariantNumeric: 'tabular-nums',
                color: 'var(--text)',
              }}
            >
              {new Intl.NumberFormat(lang, { maximumFractionDigits: 1 }).format(taAvg)}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
              {t('ar.freq.avg_label')}
            </span>
            {modeStr && (
              <>
                <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>·</span>
                <span
                  style={{
                    fontSize: '12px',
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                    color: 'var(--text-tertiary)',
                  }}
                >
                  {t('ar.freq.summary_total_mode', { mode: modeStr })}
                </span>
              </>
            )}
            {taMax != null && (
              <>
                <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>·</span>
                <span
                  style={{
                    fontSize: '12px',
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                    color: 'var(--text-tertiary)',
                  }}
                >
                  {t('ar.freq.summary_total_max', { max: taMax })}
                </span>
              </>
            )}
          </>
        )}
        {taAvg == null && (
          <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
            {t('ar.freq.summary_total_no_data')}
          </span>
        )}
      </div>

      {/* Botín medio */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '10px',
        }}
      >
        <span style={{ fontSize: '12px', color: 'var(--text-secondary)', flexShrink: 0 }}>
          {t('ar.freq.summary_bounty_label')}
        </span>
        {allZero ? (
          <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
            {t('ar.freq.summary_bounty_no_data')}
          </span>
        ) : (
          <>
            {RES_KEYS.map((res) => (
              <span key={res} style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                <ResIcon res={res} size={14} label={res} />
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                    fontSize: '13px',
                    color: 'var(--text)',
                  }}
                >
                  {new Intl.NumberFormat(lang).format(Math.round(bounty[res] ?? 0))}
                </span>
              </span>
            ))}
            <span
              style={{
                fontSize: '13px',
                fontWeight: 500,
                color: 'var(--text-secondary)',
                paddingInlineStart: '4px',
                borderInlineStart: '1px solid var(--border)',
              }}
            >
              {t('ar.freq.summary_bounty_total', {
                total: new Intl.NumberFormat(lang).format(Math.round(bounty.total ?? 0)),
              })}
            </span>
          </>
        )}
      </div>
    </div>
  )
}

// ── Sub-componente: AnimalFrequencyRow ───────────────────────────────────────
/**
 * Fila de animal v5: icono + nombre + cifra media protagonista (22px/600/mono)
 * + "animales de media" + caption con moda + peor caso.
 * Spec §8.3 + §6A.
 */
function AnimalFrequencyRow({ animal, lang, t, isMobile }) {
  const {
    animal_name,
    ordinal,
    icon_url,
    avg_present,
    mode_present,
    max_present,
    n_valid,
    n_total,
  } = animal

  const isNull = avg_present == null

  // Cifra protagonista
  let avgDisplay
  if (isNull) {
    avgDisplay = <span style={{ fontSize: '22px', color: 'var(--text-disabled)' }}>—</span>
  } else if (avg_present < 1) {
    avgDisplay = (
      <span
        style={{
          fontSize: isMobile ? '20px' : '22px',
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
          fontVariantNumeric: 'tabular-nums',
          color: 'var(--text)',
        }}
      >
        {t('ar.freq.avg_less_than_one')}
      </span>
    )
  } else {
    avgDisplay = (
      <span
        style={{
          fontSize: isMobile ? '20px' : '22px',
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
          fontVariantNumeric: 'tabular-nums',
          color: 'var(--text)',
        }}
      >
        {new Intl.NumberFormat(lang, { maximumFractionDigits: 1 }).format(avg_present)}
      </span>
    )
  }

  // Caption: moda + peor + ataques
  const modeArr = Array.isArray(mode_present) ? mode_present : []
  let modeStr = null
  if (modeArr.length >= 2) {
    modeStr = t('ar.freq.mode_tie', { a: modeArr[0], b: modeArr[1] })
  } else if (modeArr.length === 1) {
    modeStr = `${modeArr[0]}`
  }

  const hasPartialAttacks = n_valid != null && n_total != null && n_valid < n_total
  const attackLabel = hasPartialAttacks
    ? t('ar.freq.n_label_partial', { valid: n_valid, total: n_total })
    : t('ar.freq.n_label', { n: n_total ?? n_valid ?? 0 })

  const captionParts = []
  if (modeStr) captionParts.push(t('ar.freq.mode_label', { mode: modeStr }))
  if (max_present != null) captionParts.push(t('ar.freq.worst_label', { max: max_present }))
  captionParts.push(attackLabel)
  const captionLine = captionParts.join('  ·  ')

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '12px',
        paddingBlock: '14px',
        borderBottom: '1px solid var(--border)',
      }}
    >
      {/* Icono del animal */}
      <div style={{ paddingTop: '2px', flexShrink: 0 }}>
        <NatureIcon ordinal={ordinal} name={animal_name} size={22} />
      </div>

      {/* Nombre + media + caption */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: '8px',
            flexWrap: 'wrap',
          }}
        >
          <span
            style={{
              fontSize: '14px',
              fontWeight: 500,
              color: isNull ? 'var(--text-disabled)' : 'var(--text)',
            }}
          >
            {animal_name}
          </span>
          {isNull ? (
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
              {t('ar.freq.no_data_detail')}
            </span>
          ) : null}
        </div>

        {/* Cifra media protagonista */}
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: '6px',
            marginBlockStart: '2px',
          }}
        >
          {avgDisplay}
          {!isNull && (
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {t('ar.freq.avg_label')}
            </span>
          )}
        </div>

        {/* Caption: moda · peor · ataques */}
        {!isNull && captionLine && (
          <p
            style={{
              fontSize: '12px',
              color: 'var(--text-tertiary)',
              fontFamily: 'var(--font-mono)',
              fontVariantNumeric: 'tabular-nums',
              marginBlockStart: '2px',
            }}
          >
            {captionLine}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Sub-componente: TypeEmptyState ───────────────────────────────────────────
function TypeEmptyState({ typeName, t }) {
  return (
    <div
      style={{
        paddingBlock: '40px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '8px',
        textAlign: 'center',
      }}
    >
      <svg
        aria-hidden="true"
        width="28"
        height="28"
        viewBox="0 0 24 24"
        fill="none"
        stroke="var(--text-disabled)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
      </svg>
      <p style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)', maxWidth: '320px' }}>
        {t('ar.freq.type_empty_title', { type: typeName })}
      </p>
      <p style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>
        {t('ar.freq.type_empty_hint')}
      </p>
    </div>
  )
}

// ── Sub-componente: Skeleton ─────────────────────────────────────────────────
function FreqSkeleton({ t }) {
  const barStyle = (w, h = 14) => ({
    height: `${h}px`,
    width: w,
    borderRadius: 'var(--radius-sm)',
    background: 'var(--border)',
    animation: 'freq-pulse 1.5s ease-in-out infinite',
  })

  return (
    <>
      <style>{`
        @keyframes freq-pulse {
          0%, 100% { opacity: 0.5; }
          50% { opacity: 1; }
        }
        @media (prefers-reduced-motion: reduce) {
          @keyframes freq-pulse { from { opacity: 0.5; } to { opacity: 0.5; } }
        }
      `}</style>
      <div
        role="status"
        aria-label={t('ar.freq.loading')}
        aria-live="polite"
        style={{ paddingBlock: '8px' }}
      >
        {/* Skeleton de pestañas */}
        <div style={{ display: 'flex', gap: '16px', marginBlockEnd: '20px', borderBottom: '1px solid var(--border)', paddingBlockEnd: '10px' }}>
          {[70, 55, 65, 60, 80].map((w, i) => (
            <div key={i} style={barStyle(`${w}px`, 16)} />
          ))}
        </div>
        {/* Skeleton de ficha (2 barras) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBlockEnd: '20px' }}>
          <div style={barStyle('70%', 14)} />
          <div style={barStyle('50%', 14)} />
        </div>
        {/* Skeleton de 3 filas de animal */}
        {[1, 2, 3].map((i) => (
          <div key={i} style={{ display: 'flex', gap: '12px', paddingBlock: '14px', borderBottom: '1px solid var(--border)' }}>
            <div style={barStyle('22px', 22)} />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={barStyle('40%', 14)} />
              <div style={barStyle('24px', 22)} />
              <div style={barStyle('60%', 12)} />
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

// ── Panel principal: AnimalFrequencyPanel ────────────────────────────────────
/**
 * Props:
 *   data            — respuesta de getAnimalTemporalDistribution() o null
 *   loading         — boolean
 *   error           — string | null
 *   intervalMinutes — number (valor activo)
 *   onIntervalChange — (minutes: number) => void
 *   onRetry         — () => void
 *   onGoToIngest    — () => void
 *   lang            — string
 *   t               — función de traducción
 */
export function AnimalFrequencyPanel({ data: rawData, loading, error, intervalMinutes, onIntervalChange, onRetry, onGoToIngest, lang, t }) {
  // Normalizar la respuesta del backend (array → objeto, arcilla → barro, animal_ordinal → ordinal)
  // useMemo: identidad estable atada a rawData. Sin esto, `data` se recreaba en cada render,
  // disparando el useEffect de reset de pestaña y revirtiendo la selección del usuario (bug: siempre Barro).
  const data = useMemo(() => normalizeResponse(rawData), [rawData])

  // Pestaña activa — gestión interna
  const [activeType, setActiveType] = useState(null)

  // Determinar primer tipo con datos (spec §7.5)
  const firstTypeWithData = useCallback((responseData) => {
    if (!responseData?.types) return null
    for (const key of TYPE_ORDER) {
      if (key === 'sin_clasificar') continue // sin_clasificar nunca es default
      if ((responseData.types[key]?.n_reports_in_section ?? 0) > 0) return key
    }
    return null
  }, [])

  // Resetear pestaña activa cuando llegan nuevos datos
  useEffect(() => {
    if (!loading && !error && data) {
      setActiveType(firstTypeWithData(data))
    }
  }, [data, loading, error, firstTypeWithData])

  // ── Labels de frecuencia
  const intervalLabel = freqLabel(intervalMinutes)

  // ── Estado vacío global (BD completamente vacía)
  const isGlobalEmpty = !loading && !error && data?.is_empty_db === true

  // ── Estado vacío de frecuencia (ningún tipo tiene datos)
  const isFreqEmpty = !loading && !error && data && !data.is_empty_db &&
    TYPE_ORDER.every(k => (data.types?.[k]?.n_reports_in_section ?? 0) === 0)

  // ── Datos del tipo activo
  const activeTypeData = activeType ? data?.types?.[activeType] : null
  const activeTypeHasData = (activeTypeData?.n_reports_in_section ?? 0) > 0

  // ── Label del tipo activo
  const typeLabels = {
    hierro: t('ar.freq.type.hierro'),
    barro: t('ar.freq.type.barro'),
    madera: t('ar.freq.type.madera'),
    cereal: t('ar.freq.type.cereal'),
    sin_clasificar: t('ar.freq.type.sin_clasificar'),
  }
  const activeLabelStr = activeType ? (typeLabels[activeType] ?? activeType) : ''

  // ── Animales del tipo activo ordenados (null al final)
  const animals = activeTypeHasData
    ? [...(activeTypeData?.animals ?? [])].sort((a, b) => {
        const aNull = a.avg_present == null
        const bNull = b.avg_present == null
        if (aNull && !bNull) return 1
        if (!aNull && bNull) return -1
        return (b.avg_present ?? 0) - (a.avg_present ?? 0)
      })
    : []

  // ── Estado vacío global ────────────────────────────────────────────────────
  if (isGlobalEmpty) {
    return (
      <section
        aria-labelledby="freq-panel-title"
        style={{ paddingBlock: '24px 0', marginBlockEnd: '24px' }}
      >
        <h2
          id="freq-panel-title"
          style={{ fontSize: '17px', fontWeight: 600, color: 'var(--text)', marginBlockEnd: '24px' }}
        >
          {t('ar.freq.panel_title')}
        </h2>
        <div
          style={{
            paddingBlock: '48px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '12px',
            textAlign: 'center',
          }}
        >
          <svg aria-hidden="true" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--text-disabled)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
          <p style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text)' }}>
            {t('ar.freq.empty_global_title')}
          </p>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '320px' }}>
            {t('ar.freq.empty_global_body')}
          </p>
          <button
            type="button"
            onClick={onGoToIngest}
            style={{
              marginBlockStart: '4px',
              padding: '8px 20px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--btn-primary-bg)',
              color: 'var(--btn-primary-text)',
              border: 'none',
              fontSize: '14px',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'background var(--dur-fast)',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--btn-primary-hover)' }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--btn-primary-bg)' }}
          >
            {t('ar.freq.empty_global_cta')}
          </button>
        </div>
      </section>
    )
  }

  return (
    <section
      aria-labelledby="freq-panel-title"
      style={{ paddingBlock: '24px 0', marginBlockEnd: '24px' }}
    >
      {/* Título del panel */}
      <h2
        id="freq-panel-title"
        style={{ fontSize: '17px', fontWeight: 600, color: 'var(--text)', marginBlockEnd: '24px' }}
      >
        {t('ar.freq.panel_title')}
      </h2>

      {/* FrequencySelector — siempre visible (excepto vacío global) */}
      <FrequencySelector
        value={intervalMinutes}
        onChange={onIntervalChange}
        disabled={loading}
        t={t}
      />

      {/* Estado error */}
      {error && !loading && (
        <div
          role="alert"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '12px 0',
          }}
        >
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span style={{ fontSize: '14px', color: 'var(--text-secondary)', flex: 1 }}>
            {t('ar.freq.error')}
          </span>
          <button
            type="button"
            onClick={onRetry}
            style={{
              padding: '4px 12px',
              fontSize: '12px',
              fontWeight: 600,
              background: 'var(--surface-2)',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              color: 'var(--text)',
            }}
          >
            {t('ar.freq.retry')}
          </button>
        </div>
      )}

      {/* Estado loading */}
      {loading && <FreqSkeleton t={t} />}

      {/* Estado vacío de frecuencia — pestañas atenuadas + mensaje */}
      {isFreqEmpty && !loading && (
        <>
          {/* Pestañas atenuadas (no interactivas) */}
          <div
            style={{
              display: 'flex',
              gap: '0',
              borderBottom: '1px solid var(--border)',
              opacity: 0.45,
              pointerEvents: 'none',
              overflowX: 'auto',
              scrollbarWidth: 'none',
            }}
          >
            {TYPE_ORDER.map((key) => (
              <button
                key={key}
                type="button"
                disabled
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px 10px',
                  fontSize: '13px',
                  fontWeight: 500,
                  color: 'var(--text-disabled)',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: '2px solid transparent',
                  marginBlockEnd: '-1px',
                  cursor: 'not-allowed',
                  whiteSpace: 'nowrap',
                }}
              >
                {typeLabels[key]}
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>—</span>
              </button>
            ))}
          </div>
          {/* Mensaje central */}
          <div
            style={{
              paddingBlock: '40px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '8px',
              textAlign: 'center',
            }}
          >
            <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--text-disabled)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="8" y1="12" x2="16" y2="12" />
            </svg>
            <p style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)' }}>
              {t('ar.freq.all_empty_title')}
            </p>
            <p style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>
              {t('ar.freq.all_empty_hint')}
            </p>
          </div>
        </>
      )}

      {/* Estado con datos — TypeTabSelector + TypeSummaryCard + AnimalList */}
      {!loading && !error && data && !isFreqEmpty && (
        <>
          {/* TypeTabSelector */}
          <TypeTabSelector
            types={data?.types ?? {}}
            activeType={activeType}
            onTypeChange={(key) => setActiveType(key)}
            t={t}
          />

          {/* Contenido del tab activo */}
          {activeType && (
            <div
              role="tabpanel"
              id={`panel-freq-${activeType}`}
              aria-labelledby={`tab-freq-${activeType}`}
              style={{ marginBlockStart: '0' }}
            >
              {activeTypeHasData ? (
                <>
                  {/* Ficha de resumen del tipo */}
                  <TypeSummaryCard
                    typeData={activeTypeData}
                    typeName={activeLabelStr}
                    intervalLabel={intervalLabel}
                    lang={lang}
                    t={t}
                  />

                  {/* Nota contextual — Sin clasificar */}
                  {activeType === 'sin_clasificar' && (
                    <p
                      style={{
                        fontSize: '12px',
                        color: 'var(--text-tertiary)',
                        paddingBlock: '12px 0',
                        paddingInline: '0',
                      }}
                    >
                      {t('ar.freq.unclassified_note')}
                    </p>
                  )}

                  {/* Nota contextual — Cereal */}
                  {activeType === 'cereal' && (
                    <p
                      style={{
                        fontSize: '12px',
                        color: 'var(--text-tertiary)',
                        paddingBlock: '12px 0',
                      }}
                    >
                      {t('ar.freq.cereal_note')}
                    </p>
                  )}

                  {/* Lista de animales */}
                  <div role="list" aria-label={activeLabelStr}>
                    {animals.map((animal) => (
                      <div role="listitem" key={animal.animal_name ?? animal.ordinal}>
                        <AnimalFrequencyRow
                          animal={animal}
                          lang={lang}
                          t={t}
                          isMobile={false}
                        />
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                /* Tipo sin datos */
                <TypeEmptyState typeName={activeLabelStr} t={t} />
              )}
            </div>
          )}
        </>
      )}
    </section>
  )
}
