/**
 * SpawnMechanicsPanel — Panel educativo/estático sobre la mecánica de spawn de oasis.
 *
 * Pieza 1 del spec docs/design/oasis-spawn-mechanics.md.
 *
 * - Datos ESTÁTICOS del catálogo importado (NO llama API).
 * - Colapsable: colapsado por defecto en 2ª visita (persiste en localStorage).
 * - Cuando la BD está vacía (vacíoBD=true), se despliega automáticamente.
 *
 * Contenido:
 *   - Tabla timers: Animal | Orden | Timer (min)
 *   - Tabla sets normales por tipo de oasis
 *   - Nota de anomalía
 *
 * Accesibilidad:
 *   - Header = <button> con aria-expanded + aria-controls
 *   - Chevron rota 90° (transición --dur-base)
 *   - Cuerpo: grid-template-rows 0fr→1fr
 *
 * Props:
 *   lang     — string (idioma activo, para Intl)
 *   t        — función de traducción
 *   vacíoBD  — boolean (si true, despliega automáticamente)
 *
 * i18n: stats.spawn.*
 */
import { useState, useEffect, useId } from 'react'
import { NatureIcon } from './NatureIcon.jsx'
import {
  NATURE_ORDINALS,
  SPAWN_TIMER_S,
  OASIS_TYPE_SETS,
  OASIS_TYPE_ORDER,
  formatTimerMmSs,
} from '../../utils/oasisSpawnCatalog.js'

const LS_KEY = 'spawn_panel_open'

// ── Helpers de estilo reutilizables ──────────────────────────────────────────

const sectionTitle = {
  fontSize: '12px',
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  margin: '0 0 8px 0',
}

const thStyle = {
  padding: '6px 10px',
  fontSize: '11px',
  fontWeight: 600,
  color: 'var(--text-tertiary)',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  whiteSpace: 'nowrap',
  background: 'var(--surface-2)',
  borderBottom: '1px solid var(--border)',
}

const tdStyle = {
  padding: '8px 10px',
  fontSize: '13px',
  color: 'var(--text)',
  borderBottom: '1px solid var(--border)',
  verticalAlign: 'middle',
}

// ── Sub-componente: tabla de timers ──────────────────────────────────────────
function TimersTable({ t }) {
  return (
    <section style={{ marginBottom: '16px' }}>
      <h3 style={sectionTitle}>{t('stats.spawn.timers_title')}</h3>
      <div style={{ overflowX: 'auto' }}>
        <table
          role="table"
          style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}
        >
          <thead>
            <tr>
              <th scope="col" style={{ ...thStyle, textAlign: 'start' }}>
                {t('stats.spawn.col_animal')}
              </th>
              {/* Col "Orden" — P3 en móvil (oculta en < md) */}
              <th
                scope="col"
                className="hidden md:table-cell"
                style={{ ...thStyle, textAlign: 'end' }}
              >
                {t('stats.spawn.col_order')}
              </th>
              <th scope="col" style={{ ...thStyle, textAlign: 'end' }}>
                {t('stats.spawn.col_timer')}
              </th>
            </tr>
          </thead>
          <tbody>
            {NATURE_ORDINALS.map((ordinal) => {
              const name = t(`NATURE_${ordinal}`)
              const timer = SPAWN_TIMER_S[ordinal]
              return (
                <tr key={ordinal} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={tdStyle}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <NatureIcon ordinal={ordinal} name={name} size={16} />
                      <span>{name}</span>
                    </div>
                  </td>
                  {/* Orden — P3 oculto en móvil */}
                  <td
                    className="hidden md:table-cell"
                    style={{ ...tdStyle, textAlign: 'end', color: 'var(--text-secondary)' }}
                  >
                    {ordinal}
                  </td>
                  <td
                    style={{
                      ...tdStyle,
                      textAlign: 'end',
                      fontFamily: 'var(--font-mono)',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {formatTimerMmSs(timer)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

// ── Sub-componente: tabla de sets normales ──────────────────────────────────
function SetsTable({ t }) {
  return (
    <section style={{ marginBottom: '16px' }}>
      <h3 style={sectionTitle}>{t('stats.spawn.sets_title')}</h3>
      <div style={{ overflowX: 'auto' }}>
        <table
          role="table"
          style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}
        >
          <tbody>
            {OASIS_TYPE_ORDER.map((tipo) => {
              const ordinales = OASIS_TYPE_SETS[tipo]
              return (
                <tr key={tipo} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td
                    style={{
                      ...tdStyle,
                      fontWeight: 500,
                      whiteSpace: 'nowrap',
                      width: '90px',
                    }}
                  >
                    {t(`stats.spawn.oasis_type.${tipo}`)}
                  </td>
                  <td style={{ ...tdStyle }}>
                    {/* En móvil < md: chips apilados en flex-wrap. En ≥ md: fila horizontal */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                      {ordinales.map((ordinal) => {
                        const name = t(`NATURE_${ordinal}`)
                        return (
                          <span
                            key={ordinal}
                            title={name}
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              padding: '2px 7px',
                              background: 'var(--surface-2)',
                              border: '1px solid var(--border)',
                              borderRadius: 'var(--radius-full)',
                              fontSize: '12px',
                              color: 'var(--text-secondary)',
                            }}
                          >
                            <NatureIcon ordinal={ordinal} name={name} size={14} />
                            {/* En ≥ md mostramos el nombre; en móvil solo el icono */}
                            <span className="hidden md:inline">{name}</span>
                          </span>
                        )
                      })}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

// ── Panel principal ──────────────────────────────────────────────────────────
export function SpawnMechanicsPanel({ lang: _lang, t, vacíoBD = false }) {
  const panelId = useId()
  const bodyId = `spawn-body-${panelId}`

  // Estado de apertura: localStorage persiste entre visitas.
  // Primera visita (sin clave) → abierto. Segunda visita → cerrado.
  // Si la BD está vacía → forzar abierto.
  const [isOpen, setIsOpen] = useState(() => {
    if (vacíoBD) return true
    const stored = localStorage.getItem(LS_KEY)
    if (stored === null) {
      // Primera visita: marcamos que ya vino y la dejamos abierta
      localStorage.setItem(LS_KEY, '1')
      return true
    }
    // Segunda+ visita: cerrado por defecto
    return false
  })

  // Si el prop vacíoBD cambia a true, desplegar
  useEffect(() => {
    if (vacíoBD) setIsOpen(true)
  }, [vacíoBD])

  const toggle = () => {
    setIsOpen((v) => {
      const next = !v
      localStorage.setItem(LS_KEY, next ? '1' : '0')
      return next
    })
  }

  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        marginBottom: '16px',
        overflow: 'hidden',
      }}
    >
      {/* ── Header colapsable ── */}
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={bodyId}
        onClick={toggle}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '14px 20px',
          background: 'transparent',
          border: 'none',
          borderBottom: isOpen ? '1px solid var(--border)' : 'none',
          cursor: 'pointer',
          textAlign: 'start',
          outline: 'none',
          transition: 'background var(--dur-fast)',
          // Foco visible (spec §10)
          ':focus-visible': {
            outline: '2px solid var(--accent)',
            outlineOffset: '-2px',
          },
        }}
        onFocus={(e) => {
          e.currentTarget.style.outline = '2px solid var(--accent)'
          e.currentTarget.style.outlineOffset = '-2px'
        }}
        onBlur={(e) => {
          e.currentTarget.style.outline = ''
          e.currentTarget.style.outlineOffset = ''
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-2)' }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
      >
        {/* Chevron: rota 90° al abrir */}
        <span
          aria-hidden="true"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '16px',
            height: '16px',
            color: 'var(--text-tertiary)',
            transform: isOpen ? 'rotate(90deg)' : 'rotate(0deg)',
            transition: 'transform var(--dur-base) var(--ease)',
            flexShrink: 0,
          }}
        >
          {/* Chevron SVG right */}
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M3 2L7 5L3 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </span>

        {/* Título + caption */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', flex: 1 }}>
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text)' }}>
            {t('stats.spawn.panel_title')}
          </span>
          {!isOpen && (
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
              {t('stats.spawn.panel_caption')}
            </span>
          )}
        </div>
      </button>

      {/* ── Cuerpo colapsable: grid-template-rows 0fr → 1fr ── */}
      <div
        id={bodyId}
        role="region"
        aria-labelledby={`spawn-hdr-${panelId}`}
        style={{
          display: 'grid',
          gridTemplateRows: isOpen ? '1fr' : '0fr',
          transition: 'grid-template-rows var(--dur-base) var(--ease)',
        }}
      >
        <div style={{ overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px' }}>
            <TimersTable t={t} />
            <SetsTable t={t} />

            {/* Nota anomalía */}
            <div
              role="note"
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '8px',
                padding: '10px 12px',
                background: 'var(--surface-2)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '12px',
                color: 'var(--text-secondary)',
              }}
            >
              <span
                aria-hidden="true"
                style={{ color: 'var(--info)', fontSize: '13px', flexShrink: 0 }}
              >
                ⓘ
              </span>
              <span>{t('stats.spawn.anomaly_note')}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Animación reducida */}
      <style>{`
        @media (prefers-reduced-motion: reduce) {
          [id^="spawn-body-"] { transition: none !important; }
          [aria-controls^="spawn-body-"] span[aria-hidden] { transition: none !important; }
        }
      `}</style>
    </div>
  )
}
