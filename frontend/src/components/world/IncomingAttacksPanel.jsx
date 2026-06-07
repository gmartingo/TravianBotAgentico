/**
 * IncomingAttacksPanel — Nivel 2. Panel de ataques entrantes en WorldSpacePage.
 *
 * Spec:  docs/design/aviso-ataque-mundos.md §6.2, §6.3, §7.2, §8, §9, §10, §11, §12
 * Mockup: frontend/mockups/aviso-ataque-mundos.playground.html
 *
 * Componentes internos:
 *   TroopChip       — chip compacto: tipo de tropa × cantidad
 *   AttackRow       — fila de un ataque individual dentro de una tarjeta de aldea
 *   VillageAttackCard — tarjeta de una aldea propia bajo ataque
 *   IncomingAttacksPanel — panel principal con polling 20s
 *
 * Estados cubiertos (spec §7.2):
 *   sin-sesión / cargando / sin-ataques / detectado-sin-detalle /
 *   detalle-completo / mixto / error-primer-fetch / error-polling /
 *   impacto-inminente (pulso ≤60s) / countdown-en-cero
 *
 * Datos:
 *   GET /game/incoming-attacks/:worldId → { items: VillageAttacks[] }
 *   Polling cada 20 s (setInterval, mismo patrón que agentStatus en WorldSpacePage).
 *
 * Accesibilidad (spec §10):
 *   - aria-live="polite" en el contenedor: anuncia cambios sin interrumpir.
 *   - Countdown: aria-live="off" (heredado de Countdown.jsx).
 *   - "Detectado · sin detalle": badge con texto, nunca solo color.
 *   - Impacto inminente: pulso CSS respeta prefers-reduced-motion.
 *   - Contraste: var(--danger) sobre fondo 10% danger ≥ 4.5:1.
 *
 * RTL (spec §11):
 *   Todas las propiedades de espaciado usan inlineStart/inlineEnd (lógicas CSS).
 *   Coordenadas (x|y) permanecen en LTR (datos de juego).
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api } from '../../api/client.js'
import { Countdown, ExactTime } from './Countdown.jsx'

// ── CSS de la animación de pulso (inyectada una vez en el <head>) ─────────────
// Respeta prefers-reduced-motion según spec §10 / DESIGN.md §10.
const PULSE_CSS = `
@keyframes radar-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.6; }
}
.radar-imminent {
  animation: radar-pulse 2s ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  .radar-imminent { animation: none; }
}
`

function injectPulseCSS() {
  if (document.getElementById('radar-pulse-css')) return
  const style = document.createElement('style')
  style.id = 'radar-pulse-css'
  style.textContent = PULSE_CSS
  document.head.appendChild(style)
}

// ── Iconos inline ─────────────────────────────────────────────────────────────

function IconShieldAlert({ size = 16 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flexShrink: 0 }}
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  )
}

function IconShieldCheck({ size = 40 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <polyline points="9 12 11 14 15 10" />
    </svg>
  )
}

function IconLock({ size = 36 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

// ── Formatea coordenadas con signo − Unicode (U+2212) (spec §9) ───────────────
function formatCoords(x, y) {
  const fx = x < 0 ? `−${Math.abs(x)}` : String(x)
  const fy = y < 0 ? `−${Math.abs(y)}` : String(y)
  return `(${fx}|${fy})`
}

// ── TroopChip — chip compacto de tropa ───────────────────────────────────────
/**
 * Props:
 *   type  {string} — tipo de tropa (nombre clave o nombre legible)
 *   count {number} — cantidad
 *
 * Diseño (spec §6.3 "Chip de tropa"):
 *   tipo + "×" + cantidad, sin coma entre chips.
 *   Tamaño 11px, fondo var(--surface-2), borde var(--border).
 */
function TroopChip({ type, count }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '3px',
        padding: '2px 7px',
        borderRadius: 'var(--radius-full)',
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        fontSize: '11px',
        color: 'var(--text-secondary)',
        whiteSpace: 'nowrap',
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      <span>{type}</span>
      <span aria-hidden="true">×</span>
      <span>{count}</span>
    </span>
  )
}

// ── AttackRow — fila de un ataque individual ──────────────────────────────────
/**
 * Props:
 *   attack  {object}  — datos del ataque (arrival_iso, attacker_name, …)
 *   index   {number}  — índice base-1 para la etiqueta "ATAQUE N"
 *   t       {func}
 */
function AttackRow({ attack, index, t }) {
  const {
    arrival_iso,
    attacker_name,
    origin_village_name,
    origin_x,
    origin_y,
    attacker_tribe,
    alliance,
    population,
    distance,
    troops,
  } = attack

  // Calcular si el ataque es inminente (≤60s) — para el pulso CSS
  const secsRemaining = attack.seconds_remaining
  const isImminent = typeof secsRemaining === 'number' && secsRemaining <= 60

  const hasDetail = !!attacker_name

  return (
    <div
      style={{
        paddingTop: '10px',
        paddingBottom: '10px',
      }}
    >
      {/* Etiqueta "ATAQUE N — countdown · hora exacta" */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          flexWrap: 'wrap',
          gap: '6px',
          marginBottom: hasDetail ? '6px' : 0,
        }}
      >
        {/* Label ATAQUE N */}
        <span
          style={{
            fontSize: '11px',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            color: 'var(--text-secondary)',
            fontWeight: 500,
            flexShrink: 0,
          }}
        >
          {t('radar.attack.label', { n: index })} —
        </span>

        {/* Countdown HH:MM:SS */}
        <Countdown
          targetIso={arrival_iso}
          className={isImminent ? 'radar-imminent' : ''}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '13px',
            fontWeight: 600,
            fontVariantNumeric: 'tabular-nums',
            color: isImminent ? 'var(--danger)' : 'var(--text)',
          }}
        />

        {/* Separador · hora exacta */}
        {arrival_iso && (
          <>
            <span style={{ color: 'var(--text-tertiary)', flexShrink: 0 }}>·</span>
            <ExactTime
              targetIso={arrival_iso}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
                color: 'var(--text-tertiary)',
                fontVariantNumeric: 'tabular-nums',
              }}
            />
          </>
        )}
      </div>

      {/* Datos del atacante */}
      {!hasDetail ? (
        /* "Detectado · sin detalle" — badge gris con texto (spec §6.3, §10) */
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: '2px 8px',
            borderRadius: 'var(--radius-full)',
            background: 'var(--surface-2)',
            color: 'var(--text-secondary)',
            fontSize: '11px',
            fontWeight: 500,
          }}
          aria-label={t('radar.attack.detected')}
        >
          {t('radar.attack.detected')}
        </span>
      ) : (
        /* Detalle completo del atacante */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>

          {/* Línea 1: nombre del atacante */}
          <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text)' }}>
            {attacker_name}
          </div>

          {/* Línea 2 (P2 en móvil): aldea de origen + coords */}
          {(origin_village_name || (origin_x != null && origin_y != null)) && (
            <div
              className="md:block hidden"
              style={{ fontSize: '12px', color: 'var(--text-secondary)' }}
            >
              {origin_village_name && (
                <span>{origin_village_name}</span>
              )}
              {origin_x != null && origin_y != null && (
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    marginInlineStart: origin_village_name ? '4px' : 0,
                    color: 'var(--text-tertiary)',
                    direction: 'ltr',
                    unicodeBidi: 'isolate',
                  }}
                >
                  {formatCoords(origin_x, origin_y)}
                </span>
              )}
            </div>
          )}

          {/* Línea 3 (P2 en móvil): tribu · alianza · pob · distancia */}
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            {/* Tribu — P1 (siempre visible) */}
            {attacker_tribe && (
              <span>{t(`tribe.${attacker_tribe}`)}</span>
            )}

            {/* Alianza — P2 en móvil */}
            {alliance && (
              <span className="md:inline hidden">
                {' · '}
                <span>[{alliance}]</span>
              </span>
            )}

            {/* Población — P2 en móvil */}
            {population != null && (
              <span className="md:inline hidden">
                {' · '}
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {t('radar.attack.population')} {population.toLocaleString()}
                </span>
              </span>
            )}

            {/* Distancia — P2 en móvil (spec §11, mismo criterio que alianza/pob) */}
            {distance != null && (
              <span className="md:inline hidden">
                {' · '}
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {`Dist. ${distance.toFixed(2).replace('.', ',')} ${t('radar.attack.distance')}`}
                </span>
              </span>
            )}
          </div>

          {/* Tropas — P1 (siempre visibles, flex-wrap en móvil) */}
          {troops && troops.length > 0 && (
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '4px',
                marginTop: '4px',
              }}
              aria-label={t('radar.attack.troops')}
            >
              {troops.map((troop, i) => (
                <TroopChip key={i} type={troop.type} count={troop.count} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── VillageAttackCard — tarjeta de una aldea propia bajo ataque ───────────────
/**
 * Props:
 *   villageName {string}
 *   coordsX     {number}
 *   coordsY     {number}
 *   attacks     {Attack[]}
 *   t           {func}
 */
function VillageAttackCard({ villageName, coordsX, coordsY, attacks, t }) {
  const count = attacks.length

  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '12px 16px',
        marginBottom: '12px',
      }}
    >
      {/* Cabecera de la tarjeta: nombre aldea + coords (P2 en móvil) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '8px',
          marginBottom: '8px',
        }}
      >
        <span
          style={{
            fontSize: '15px',
            fontWeight: 600,
            color: 'var(--text)',
          }}
        >
          {villageName}
        </span>

        {/* Coords P2 — ocultas en < md */}
        {coordsX != null && coordsY != null && (
          <span
            className="md:inline hidden"
            style={{
              fontSize: '12px',
              fontFamily: 'var(--font-mono)',
              color: 'var(--text-tertiary)',
              direction: 'ltr',
              unicodeBidi: 'isolate',
            }}
          >
            {formatCoords(coordsX, coordsY)}
          </span>
        )}

        {/* Badge de nº de ataques por aldea */}
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: '1px 8px',
            borderRadius: 'var(--radius-full)',
            background: 'color-mix(in srgb, var(--danger) 10%, transparent)',
            border: '1px solid color-mix(in srgb, var(--danger) 25%, transparent)',
            color: 'var(--danger)',
            fontSize: '12px',
            fontWeight: 500,
            marginInlineStart: 'auto',
          }}
        >
          {count === 1
            ? t('radar.village.attacks_one')
            : t('radar.village.attacks_other', { count })}
        </span>
      </div>

      {/* Lista de ataques separados por hairline */}
      {attacks.map((attack, i) => (
        <div key={i}>
          {i > 0 && (
            <div
              style={{
                borderTop: '1px solid var(--border)',
                marginTop: '0',
              }}
              aria-hidden="true"
            />
          )}
          <AttackRow attack={attack} index={i + 1} t={t} />
        </div>
      ))}
    </div>
  )
}

// ── SkeletonCard — placeholder de carga ──────────────────────────────────────
function SkeletonCard() {
  return (
    <div
      aria-hidden="true"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '16px',
        marginBottom: '12px',
      }}
    >
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
        <span style={{
          display: 'block', height: '16px', width: '120px',
          borderRadius: '4px', background: 'var(--surface-2)',
          animation: 'pulse 1.2s ease-in-out infinite',
        }} />
        <span style={{
          display: 'block', height: '16px', width: '60px',
          borderRadius: '4px', background: 'var(--surface-2)',
          animation: 'pulse 1.2s ease-in-out infinite',
        }} />
      </div>
      <span style={{
        display: 'block', height: '13px', width: '80%',
        borderRadius: '4px', background: 'var(--surface-2)',
        animation: 'pulse 1.2s ease-in-out infinite',
        marginBottom: '8px',
      }} />
      <span style={{
        display: 'block', height: '13px', width: '60%',
        borderRadius: '4px', background: 'var(--surface-2)',
        animation: 'pulse 1.2s ease-in-out infinite',
      }} />
    </div>
  )
}

// ── IncomingAttacksPanel ──────────────────────────────────────────────────────
/**
 * Props:
 *   worldId       {number}  — ID del mundo activo
 *   sessionActive {boolean} — si hay sesión activa. Sin sesión → no hace polling.
 *   onCountChange {func}    — callback(count) para el nav-badge del sidebar.
 *
 * Estados internos:
 *   phase: 'loading' | 'ok' | 'error-initial' | 'no-session'
 *   items: VillageAttacks[]
 *   pollingError: boolean   — true si un ciclo de polling falló (pero hay datos previos)
 *   lastUpdated: number     — timestamp del último fetch exitoso
 *   secondsSinceUpdate: number — contador visual de frescura
 */
export function IncomingAttacksPanel({ worldId, sessionActive = true, onCountChange }) {
  const { t } = useI18n()

  const [phase, setPhase] = useState('loading')
  const [items, setItems] = useState([])
  const [pollingError, setPollingError] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null) // Date.now() al recibir datos
  const [secondsSinceUpdate, setSecondsSinceUpdate] = useState(0)
  const [checking, setChecking] = useState(false)      // botón debug: forzar /check
  const [checkMsg, setCheckMsg] = useState(null)

  const hasLoadedOnce = useRef(false)
  const isMounted = useRef(true)

  // Inyectar CSS de animación de pulso (una vez)
  useEffect(() => {
    injectPulseCSS()
  }, [])

  // ── Conteo total de ataques (para el nav-badge) ───────────────────────────
  const totalAttacks = items.reduce((acc, village) => acc + (village.attacks?.length ?? 0), 0)

  // Notificar al padre cuando cambia el conteo
  useEffect(() => {
    onCountChange?.(totalAttacks)
  }, [totalAttacks]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Fetch de ataques ──────────────────────────────────────────────────────
  const fetchAttacks = useCallback(async () => {
    if (!sessionActive) return
    try {
      const data = await api.getIncomingAttacks(worldId)
      if (!isMounted.current) return
      const incoming = data?.items ?? []
      setItems(incoming)
      setPollingError(false)
      setLastUpdated(Date.now())
      setSecondsSinceUpdate(0)
      if (!hasLoadedOnce.current) {
        setPhase('ok')
        hasLoadedOnce.current = true
      }
    } catch {
      if (!isMounted.current) return
      if (!hasLoadedOnce.current) {
        setPhase('error-initial')
      } else {
        // Error de polling: mantener datos anteriores, mostrar aviso inline
        setPollingError(true)
      }
    }
  }, [worldId, sessionActive])

  // ── DEBUG: forzar detección inmediata (POST /check) ───────────────────────
  const forceCheck = useCallback(async () => {
    setChecking(true)
    setCheckMsg(null)
    try {
      const res = await api.checkIncomingAttacks(worldId)
      if (!isMounted.current) return
      const n = res?.attacks_detected ?? 0
      setCheckMsg(`✓ ${n} ataque(s) detectado(s)`)
      await fetchAttacks()
    } catch (err) {
      if (!isMounted.current) return
      const isTimeout = err?.detail === 'timeout' || err?.status === 0
      if (isTimeout) {
        setCheckMsg('✕ timeout — el check tardó más de 15 s')
      } else if (err?.status === 409) {
        // 409 = el WorldAgent no está RUNNING (distinto de "sin sesión"): el
        // radar manual depende del agente, no solo del login. Guiar al toggle.
        setCheckMsg('✕ el Agente no está activo — arráncalo con el toggle «Agente»')
      } else {
        const code = err?.status ? ` (${err.status})` : ''
        setCheckMsg(`✕ error${code} — ¿sesión activa en el mundo?`)
      }
    } finally {
      if (isMounted.current) setChecking(false)
    }
  }, [worldId, fetchAttacks])

  // ── Ciclo de polling 20 s ─────────────────────────────────────────────────
  useEffect(() => {
    isMounted.current = true
    hasLoadedOnce.current = false

    if (!sessionActive) {
      setPhase('no-session')
      return
    }

    setPhase('loading')
    fetchAttacks()

    const pollId = setInterval(fetchAttacks, 20_000)
    return () => {
      isMounted.current = false
      clearInterval(pollId)
    }
  }, [worldId, sessionActive, fetchAttacks])

  // ── Contador de frescura (segundos desde el último update) ───────────────
  useEffect(() => {
    if (!lastUpdated) return
    const id = setInterval(() => {
      setSecondsSinceUpdate(Math.floor((Date.now() - lastUpdated) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [lastUpdated])

  // ── DEBUG: barra con botón "Forzar detección" — visible en TODOS los estados ─
  const debugBar = (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px', flexWrap: 'wrap' }}>
      <button
        type="button"
        onClick={forceCheck}
        disabled={checking}
        style={{
          fontSize: '13px', fontWeight: 500, padding: '6px 12px',
          borderRadius: '8px', border: '1px solid var(--border)',
          background: 'var(--surface)', color: 'var(--text)',
          cursor: checking ? 'wait' : 'pointer', fontFamily: 'inherit',
        }}
      >
        {checking ? '⏳ Detectando…' : '🛡 Forzar detección (debug)'}
      </button>
      {checkMsg && (
        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{checkMsg}</span>
      )}
    </div>
  )

  // ── RENDER: sin sesión ────────────────────────────────────────────────────
  if (phase === 'no-session') {
    return (
      <>
        {debugBar}
        <div
          style={{
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: '12px', padding: '32px 24px', textAlign: 'center',
            color: 'var(--text-tertiary)',
          }}
        >
          <IconLock size={36} />
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', maxWidth: '280px' }}>
            {t('radar.panel.no_session')}
          </p>
        </div>
      </>
    )
  }

  // ── RENDER: sin sesión (variante antigua, ya sustituida arriba) ────────────
  if (false) {
    return (
      <div
        style={{
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          gap: '12px', padding: '48px 24px', textAlign: 'center',
          color: 'var(--text-tertiary)',
        }}
      >
        <IconLock size={36} />
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', maxWidth: '280px' }}>
          {t('radar.panel.no_session')}
        </p>
      </div>
    )
  }

  // ── RENDER: cargando (primer fetch) ──────────────────────────────────────
  if (phase === 'loading') {
    return (
      <>
        {debugBar}
        <div aria-busy="true" aria-label={t('radar.panel.empty.title')}>
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </>
    )
  }

  // ── RENDER: error primer fetch ────────────────────────────────────────────
  if (phase === 'error-initial') {
    return (
      <>
      {debugBar}
      <div
        style={{
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          gap: '14px', padding: '48px 24px', textAlign: 'center',
        }}
      >
        <div style={{
          width: '48px', height: '48px', borderRadius: '50%',
          background: 'var(--surface-2)',
          display: 'grid', placeItems: 'center',
          color: 'var(--text-tertiary)',
        }}>
          <IconShieldAlert size={24} />
        </div>
        <p style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text)' }}>
          {t('radar.panel.error.title')}
        </p>
        <button
          type="button"
          onClick={() => { hasLoadedOnce.current = false; setPhase('loading'); fetchAttacks() }}
          style={{
            height: '32px', padding: '0 16px',
            borderRadius: 'var(--radius-sm)',
            border: 'none',
            background: 'var(--btn-primary-bg)',
            color: 'var(--btn-primary-text)',
            fontSize: '13px', fontWeight: 500,
            cursor: 'pointer', fontFamily: 'inherit',
            transition: 'background var(--dur-fast)',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--btn-primary-hover)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'var(--btn-primary-bg)' }}
        >
          {t('radar.panel.retry')}
        </button>
      </div>
      </>
    )
  }

  // ── RENDER: estado OK (con o sin ataques) ─────────────────────────────────
  const villagesWithAttacks = items.filter(v => v.attacks?.length > 0)
  const isEmpty = villagesWithAttacks.length === 0

  return (
    <div aria-live="polite" aria-atomic="false">

      {debugBar}

      {/* Cabecera del panel */}
      {!isEmpty && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '12px',
            flexWrap: 'wrap',
          }}
        >
          <span style={{ color: 'var(--danger)', display: 'flex', alignItems: 'center' }}>
            <IconShieldAlert size={16} />
          </span>
          <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text)', flex: 1 }}>
            {totalAttacks === 1
              ? t('radar.panel.title_one', { villages: villagesWithAttacks.length })
              : t('radar.panel.title_other', { count: totalAttacks, villages: villagesWithAttacks.length })
            }
          </span>
          {lastUpdated && (
            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginInlineStart: 'auto' }}>
              {t('radar.panel.updated', { n: secondsSinceUpdate })}
            </span>
          )}
        </div>
      )}

      {/* Aviso de error de polling (inline, no bloquea el contenido) */}
      {pollingError && !isEmpty && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            marginBottom: '10px',
            fontSize: '12px',
            color: 'var(--text-secondary)',
          }}
        >
          <span>{t('radar.panel.error.inline')}</span>
          <button
            type="button"
            onClick={() => { setPollingError(false); fetchAttacks() }}
            style={{
              fontSize: '12px',
              color: 'var(--accent-text)',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              fontFamily: 'inherit',
              padding: 0,
              textDecoration: 'underline',
              textUnderlineOffset: '2px',
            }}
          >
            {t('radar.panel.retry')}
          </button>
        </div>
      )}

      {/* Hairline separador */}
      {!isEmpty && (
        <div
          style={{ borderTop: '1px solid var(--border)', marginBottom: '16px' }}
          aria-hidden="true"
        />
      )}

      {/* Estado vacío — ShieldCheck + texto */}
      {isEmpty && (
        <div
          style={{
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: '12px', padding: '48px 24px', textAlign: 'center',
          }}
        >
          <div style={{ color: 'var(--success)' }}>
            <IconShieldCheck size={40} />
          </div>
          <p style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text)', margin: 0 }}>
            {t('radar.panel.empty.title')}
          </p>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0, maxWidth: '280px' }}>
            {t('radar.panel.empty.desc')}
          </p>
        </div>
      )}

      {/* Tarjetas de aldea (scroll interno si el contenido crece, spec §6.3) */}
      {!isEmpty && (
        <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 300px)' }}>
          {villagesWithAttacks.map((village, i) => (
            <VillageAttackCard
              key={`${village.village_name}-${village.coords_x}-${village.coords_y}-${i}`}
              villageName={village.village_name}
              coordsX={village.coords_x}
              coordsY={village.coords_y}
              attacks={village.attacks}
              t={t}
            />
          ))}
        </div>
      )}
    </div>
  )
}
