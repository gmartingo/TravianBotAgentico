/**
 * OasisCombatPlannerPanel — Panel fusionado de planificación de combate (v2.6).
 *
 * Spec: docs/design/oasis-spawn-mechanics.md §v2.6
 * Consume: GET /attack-reports/stats/oasis/spawn-composition?timer_min=N (EP-SPAWN)
 *
 * v2.6 — Anidado Jugador → Aldea → Oasis:
 *   - Cada oasis lleva `attackers: [{player, village}]` (backend RN-GROUP-01 v2.6).
 *     Sustituye al anterior `origin_villages: string[]` de v2.3.
 *   - Se construye un mapa anidado:
 *       player → (village → [oasis])
 *     Un oasis con N pares (player, village) aparece bajo CADA uno con los mismos datos.
 *   - NIVEL 1: sección colapsable por JUGADOR (PlayerOasisSection), expandida por defecto.
 *     Cabecera: nombre del jugador + contador discreto de aldeas.
 *   - NIVEL 2: sección colapsable por ALDEA dentro de cada jugador (CityOasisSection).
 *   - NIVEL 3: los bloques de oasis (OasisBlock) sin cambios respecto a v2.3.
 *   - Orden jugadores: A-Z, "Desconocido" siempre al final.
 *   - Orden aldeas dentro de cada jugador: A-Z, "Desconocido" siempre al final.
 *   - El selector de intervalo (6/7/10/15) sigue siendo ÚNICO arriba del panel.
 *
 * Estructura por oasis:
 *   - Cabecera: coords + OasisTypeBadge (tipo + confianza) + SpawnStatusDot (color + texto)
 *   - Selector de intervalo único (6/7/10/15 min) arriba del panel (pills, oro en activo)
 *   - Dos filas compactas de chips por oasis:
 *       Fila "Media": NatureIcon + max_present_per_burst por animal con present>0.
 *                     Anomalías aparecen aquí con badge "anom." en acento oro.
 *       Fila "Peor":  NatureIcon + worst_case_count (número plano, SIN ×) por animal
 *                     NO anómalo. Anomalías ausentes en esta fila.
 *   - Si inferred_type=null: nota "Sin tipo inferido", sin fila Peor
 *
 * IMPORTANTE (v2.2): worst_case_count es un CONTEO ABSOLUTO de animales (no un
 * multiplicador). Se muestra como número plano (ej. "13"), nunca con "×".
 *
 * Fuerzas defensivas (def_infantry_contribution / def_cavalry_contribution):
 *   El backend las sigue devolviendo. NO se muestran en la UI (eliminadas en v2.2).
 *
 * Estados: loading / error (con reintentar) / vacío (CTA) / normal /
 *          oasis sin tipo (nota inline) / animal nunca visto (ausente, no 0)
 *
 * Accesibilidad (§10):
 *   - Skeleton: role="status" aria-label
 *   - Error: role="alert"
 *   - TimerSelector: aria-pressed, aria-disabled
 *   - SpawnStatusDot: color + texto SIEMPRE
 *   - Badge anomalía: title con descripción
 *   - PlayerOasisSection: aria-expanded, aria-labelledby en <section>
 *   - CityOasisSection: aria-expanded, aria-labelledby en <section>
 *   - Foco visible en todos los controles
 *
 * Responsive (§11):
 *   - Filas de chips envuelven (flex-wrap) si hay muchos animales
 *   - Mobile: cabecera apilada, chips en una línea que wrappea
 *   - TimerSelector siempre visible (P1)
 *
 * Props:
 *   data        — respuesta EP-SPAWN (o null)
 *   loading     — boolean
 *   error       — string | null
 *   onRetry     — () => void
 *   onGoToIngest — () => void
 *   timerMin    — number (valor activo: 6|7|10|15)
 *   onTimerChange — (newTimerMin: number) => void
 *   lang        — string
 *   t           — función de traducción
 */
import { NatureIcon } from './NatureIcon.jsx'
import { CityOasisSection } from './CityOasisSection.jsx'
import { PlayerOasisSection } from './PlayerOasisSection.jsx'

// ── Clave raw del backend para entidades "desconocidas" ───────────────────────
const UNKNOWN_RAW = 'Desconocido'

/**
 * Ordena un array de [nombre, datos] poniendo UNKNOWN_RAW siempre al final.
 */
function sortEntries(entries) {
  return entries.sort(([a], [b]) => {
    if (a === UNKNOWN_RAW) return 1
    if (b === UNKNOWN_RAW) return -1
    return a.localeCompare(b)
  })
}

/**
 * Construye el mapa anidado { player → { village → [oasis...] } } a partir del
 * array de oasis. Cada oasis se añade bajo CADA par (player, village) de su
 * campo attackers. Si attackers está ausente o vacío, cae a (UNKNOWN_RAW, UNKNOWN_RAW).
 *
 * Devuelve un array:
 *   [ [playerName, [ [villageName, [oasis...]], ... ]], ... ]
 * Ordenado: jugadores A-Z con UNKNOWN_RAW al final; dentro, aldeas A-Z con UNKNOWN_RAW al final.
 */
function buildPlayerMap(oasisArray) {
  // playerMap: { playerName → { villageName → [oasis] } }
  const playerMap = {}

  for (const oasis of oasisArray) {
    const pairs =
      Array.isArray(oasis.attackers) && oasis.attackers.length > 0
        ? oasis.attackers
        : [{ player: UNKNOWN_RAW, village: UNKNOWN_RAW }]

    for (const { player, village } of pairs) {
      const p = player || UNKNOWN_RAW
      const v = village || UNKNOWN_RAW
      if (!playerMap[p]) playerMap[p] = {}
      if (!playerMap[p][v]) playerMap[p][v] = []
      playerMap[p][v].push(oasis)
    }
  }

  // Convertir a array ordenado
  const playerEntries = sortEntries(Object.entries(playerMap))
  return playerEntries.map(([playerName, villageMap]) => {
    const villageEntries = sortEntries(Object.entries(villageMap))
    return [playerName, villageEntries]
  })
}

const TIMER_OPTIONS = [6, 7, 10, 15]

// ── Helpers de formato ────────────────────────────────────────────────────────

function formatCoord(n) {
  if (n == null) return '—'
  return n < 0 ? `−${Math.abs(n)}` : `${n}`
}

// ── TimerSelector ─────────────────────────────────────────────────────────────
function TimerSelector({ value, onChange, disabled, t }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        flexWrap: 'wrap',
        marginBottom: '16px',
      }}
    >
      <span
        style={{
          fontSize: '12px',
          color: 'var(--text-secondary)',
          fontWeight: 500,
          flexShrink: 0,
        }}
      >
        {t('stats.planner.interval_label')}
      </span>
      {TIMER_OPTIONS.map((opt) => {
        const isActive = opt === value
        return (
          <button
            key={opt}
            type="button"
            aria-pressed={isActive}
            aria-disabled={disabled || undefined}
            disabled={disabled}
            onClick={() => !disabled && onChange(opt)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '4px 14px',
              borderRadius: 'var(--radius-full)',
              fontSize: '13px',
              fontWeight: isActive ? 600 : 500,
              cursor: disabled ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-mono)',
              fontVariantNumeric: 'tabular-nums',
              transition: 'background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast)',
              opacity: disabled ? 0.4 : 1,
              border: isActive
                ? '1px solid var(--accent-subtle-border)'
                : '1px solid var(--border-strong)',
              background: isActive ? 'var(--accent-subtle)' : 'var(--surface-2)',
              color: isActive ? 'var(--accent-text)' : 'var(--text)',
              outline: 'none',
            }}
            onFocus={(e) => { e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '2px' }}
            onBlur={(e)  => { e.currentTarget.style.outline = ''; e.currentTarget.style.outlineOffset = '' }}
            onMouseEnter={(e) => {
              if (!disabled && !isActive) {
                e.currentTarget.style.borderColor = 'var(--accent)'
              }
            }}
            onMouseLeave={(e) => {
              if (!disabled && !isActive) {
                e.currentTarget.style.borderColor = 'var(--border-strong)'
              }
            }}
          >
            {opt} min
          </button>
        )
      })}
    </div>
  )
}

// ── SpawnStatusDot ────────────────────────────────────────────────────────────
function SpawnStatusDot({ status, t }) {
  const colorMap = {
    respawning: { dot: 'var(--success)', text: 'var(--success)' },
    cooldown:   { dot: 'var(--danger)',  text: 'var(--danger)'  },
    unknown:    { dot: 'var(--text-disabled)', text: 'var(--text-disabled)' },
  }
  const keyMap = {
    respawning: 'stats.composition.status.respawning',
    cooldown:   'stats.composition.status.cooldown',
    unknown:    'stats.composition.status.unknown',
  }
  const { dot, text } = colorMap[status] ?? colorMap.unknown
  const label = t(keyMap[status] ?? keyMap.unknown)

  return (
    <span
      style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}
      title={label}
    >
      <span
        aria-hidden="true"
        style={{
          width: '7px',
          height: '7px',
          borderRadius: '50%',
          background: dot,
          flexShrink: 0,
          display: 'inline-block',
        }}
      />
      <span style={{ fontSize: '12px', color: text, whiteSpace: 'nowrap' }}>
        {label}
      </span>
    </span>
  )
}

// ── OasisTypeBadge ─────────────────────────────────────────────────────────
function OasisTypeBadge({ type, confidence, t }) {
  if (!type) {
    return (
      <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>—</span>
    )
  }

  const typeLabel = t(`stats.spawn.oasis_type.${type}`)
  const confLabel = confidence
    ? t(`stats.composition.confidence.${confidence === 'low' ? 'low' : 'medium'}`)
    : null

  const titleText = confLabel ? `${typeLabel} · ${confLabel}` : typeLabel

  return (
    <span
      title={titleText}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '3px',
        padding: '2px 8px',
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-full)',
        fontSize: '11px',
        fontWeight: 500,
        color: 'var(--text)',
        whiteSpace: 'nowrap',
      }}
    >
      {typeLabel}
      {confLabel && (
        <span
          style={{
            fontSize: '10px',
            color: 'var(--text-tertiary)',
            marginInlineStart: '2px',
          }}
        >
          ·{confLabel}
        </span>
      )}
    </span>
  )
}

// ── Chip de animal (fila Media o Peor) ───────────────────────────────────────
/**
 * AnimalChip — chip compacto: NatureIcon + número + badge opcional "anom."
 * rowType: 'media' | 'worst'
 * isAnomaly: solo en fila Media (en Peor los anómalos no aparecen)
 */
function AnimalChip({ ordinal, count, isAnomaly, rowType, t }) {
  const name = t(`NATURE_${ordinal}`)
  const anomalyTitle = t('stats.composition.anomaly_tooltip')

  return (
    <span
      title={isAnomaly ? `${name} · ${anomalyTitle}` : name}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '3px',
        padding: '2px 7px',
        background: isAnomaly ? 'var(--accent-subtle)' : 'var(--surface-2)',
        border: isAnomaly
          ? '1px solid var(--accent-subtle-border)'
          : '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '12px',
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
        color: isAnomaly ? 'var(--accent-text)' : 'var(--text)',
        margin: '1px',
      }}
    >
      <NatureIcon ordinal={ordinal} name={name} size={14} />
      <span>{count}</span>
      {isAnomaly && rowType === 'media' && (
        <span
          title={anomalyTitle}
          style={{
            fontSize: '9px',
            fontWeight: 600,
            color: 'var(--accent-text)',
            background: 'var(--accent-subtle)',
            border: '1px solid var(--accent-subtle-border)',
            borderRadius: 'var(--radius-full)',
            padding: '0 4px',
            marginInlineStart: '2px',
          }}
        >
          {t('stats.composition.anomaly_badge')}
        </span>
      )}
    </span>
  )
}

// ── Etiqueta de fila ──────────────────────────────────────────────────────────
function RowLabel({ children }) {
  return (
    <span
      style={{
        fontSize: '10px',
        fontWeight: 600,
        color: 'var(--text-tertiary)',
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        flexShrink: 0,
        minWidth: '36px',
        paddingTop: '3px',
      }}
    >
      {children}
    </span>
  )
}

// ── Bloque de un oasis ────────────────────────────────────────────────────────
function OasisBlock({ oasis, t }) {
  const cx = formatCoord(oasis.coord_x_dest)
  const cy = formatCoord(oasis.coord_y_dest)
  const noType = !oasis.inferred_type

  // Animales con al menos 1 presencia (avg o max > 0)
  const allSpecies = oasis.species || []
  const mediaSpecies = allSpecies.filter(
    (sp) => sp.avg_present_per_burst != null || sp.max_present_per_burst != null
  )
  // Peor: solo no anómalos con worst_case_count numérico
  const worstSpecies = allSpecies.filter(
    (sp) => !sp.is_anomaly && sp.worst_case_count != null
  )

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        marginBottom: '10px',
        overflow: 'hidden',
      }}
    >
      {/* Cabecera del oasis */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '8px',
          padding: '8px 12px',
          background: 'var(--surface-2)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        {/* Coordenadas */}
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontVariantNumeric: 'tabular-nums',
            fontSize: '13px',
            fontWeight: 600,
            color: 'var(--text)',
            whiteSpace: 'nowrap',
          }}
        >
          ({cx}|{cy})
        </span>

        {/* Badge tipo + confianza */}
        <OasisTypeBadge type={oasis.inferred_type} confidence={oasis.confidence} t={t} />

        {/* Estado spawn */}
        <SpawnStatusDot status={oasis.spawn_status ?? 'unknown'} t={t} />
      </div>

      {/* Cuerpo del oasis */}
      <div style={{ padding: '10px 12px' }}>
        {noType ? (
          /* Sin tipo inferido: nota inline */
          <div
            role="note"
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '6px',
              fontSize: '12px',
              color: 'var(--text-secondary)',
              fontStyle: 'italic',
            }}
          >
            <span aria-hidden="true" style={{ color: 'var(--info)', flexShrink: 0 }}>ⓘ</span>
            <span>{t('stats.planner.no_type_note')}</span>
          </div>
        ) : mediaSpecies.length === 0 ? (
          /* Sin species en absoluto */
          <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
            {t('stats.composition.no_data')}
          </span>
        ) : (
          /* Dos filas compactas */
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>

            {/* Fila Media */}
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
              <RowLabel>{t('stats.planner.row_media')}</RowLabel>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px' }}>
                {mediaSpecies.map((sp) => (
                  <AnimalChip
                    key={sp.animal_ordinal}
                    ordinal={sp.animal_ordinal}
                    count={sp.max_present_per_burst ?? '—'}
                    isAnomaly={sp.is_anomaly}
                    rowType="media"
                    t={t}
                  />
                ))}
              </div>
            </div>

            {/* Fila Peor — solo si hay al menos un animal no anómalo con worst_case_count */}
            {worstSpecies.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                <RowLabel>{t('stats.planner.row_worst')}</RowLabel>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px' }}>
                  {worstSpecies.map((sp) => (
                    <AnimalChip
                      key={sp.animal_ordinal}
                      ordinal={sp.animal_ordinal}
                      count={sp.worst_case_count}
                      isAnomaly={false}
                      rowType="worst"
                      t={t}
                    />
                  ))}
                </div>
              </div>
            )}

          </div>
        )}
      </div>
    </div>
  )
}

// ── Skeleton ─────────────────────────────────────────────────────────────────
function PlannerSkeleton() {
  const bar = (w) => (
    <div
      style={{
        height: '14px',
        width: w,
        borderRadius: 'var(--radius-sm)',
        background: 'var(--border)',
        animation: 'planner-pulse 1.5s ease-in-out infinite',
      }}
    />
  )
  const chip = () => (
    <div
      style={{
        height: '24px',
        width: '52px',
        borderRadius: 'var(--radius-sm)',
        background: 'var(--border)',
        animation: 'planner-pulse 1.5s ease-in-out infinite',
      }}
    />
  )

  return (
    <div
      role="status"
      aria-label="Cargando..."
      style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}
    >
      <style>{`
        @keyframes planner-pulse { 0%,100%{opacity:.6} 50%{opacity:1} }
        @media(prefers-reduced-motion:reduce){ [role="status"] div { animation:none !important; opacity:.6; } }
      `}</style>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            overflow: 'hidden',
          }}
        >
          {/* Cabecera skeleton */}
          <div
            style={{
              display: 'flex',
              gap: '10px',
              padding: '8px 12px',
              background: 'var(--surface-2)',
              borderBottom: '1px solid var(--border)',
            }}
          >
            {bar('12%')}
            {bar('16%')}
            {bar('14%')}
          </div>
          {/* Cuerpo skeleton */}
          <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ display: 'flex', gap: '6px' }}>
              {bar('8%')}
              {chip()}
              {chip()}
              {chip()}
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              {bar('8%')}
              {chip()}
              {chip()}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Error banner ──────────────────────────────────────────────────────────────
function ErrorBanner({ message, onRetry, t }) {
  return (
    <div
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '12px',
        padding: '12px 16px',
        background: 'var(--danger-subtle)',
        border: '1px solid var(--danger-border)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '13px',
        color: 'var(--danger)',
      }}
    >
      <span>{message}</span>
      <button
        type="button"
        onClick={onRetry}
        style={{
          flexShrink: 0,
          padding: 0,
          fontSize: '12px',
          fontWeight: 500,
          color: 'var(--accent-text)',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          fontFamily: 'var(--font-sans)',
          textDecoration: 'underline',
          textUnderlineOffset: '2px',
          outline: 'none',
        }}
        onFocus={(e) => { e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '2px' }}
        onBlur={(e)  => { e.currentTarget.style.outline = ''; e.currentTarget.style.outlineOffset = '' }}
      >
        {t('stats.planner.retry')}
      </button>
    </div>
  )
}

// ── Estado vacío ─────────────────────────────────────────────────────────────
function EmptyState({ onGoToIngest, t }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '32px 16px',
        gap: '8px',
        textAlign: 'center',
      }}
    >
      <span aria-hidden="true" style={{ fontSize: '28px', color: 'var(--text-tertiary)' }}>
        📋
      </span>
      <p style={{ margin: 0, fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)' }}>
        {t('stats.planner.empty_title')}
      </p>
      <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-tertiary)', maxWidth: '320px' }}>
        {t('stats.planner.empty_body')}
      </p>
      <button
        type="button"
        onClick={onGoToIngest}
        style={{
          marginTop: '8px',
          padding: '7px 16px',
          borderRadius: 'var(--radius-sm)',
          background: 'var(--btn-primary-bg)',
          color: 'var(--btn-primary-text)',
          fontSize: '13px',
          fontWeight: 500,
          border: 'none',
          cursor: 'pointer',
          fontFamily: 'var(--font-sans)',
          outline: 'none',
          transition: 'background var(--dur-fast)',
        }}
        onFocus={(e) => { e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '2px' }}
        onBlur={(e)  => { e.currentTarget.style.outline = ''; e.currentTarget.style.outlineOffset = '' }}
        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--btn-primary-hover)' }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--btn-primary-bg)' }}
      >
        {t('stats.planner.empty_cta')}
      </button>
    </div>
  )
}

// ── Panel principal ──────────────────────────────────────────────────────────
export function OasisCombatPlannerPanel({
  data,
  loading,
  error,
  onRetry,
  onGoToIngest,
  timerMin,
  onTimerChange,
  lang: _lang,
  t,
}) {
  const isEmpty = !loading && !error && (!data || data.oasis.length === 0)
  const hasData = !loading && !error && data && data.oasis.length > 0

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
      {/* Header */}
      <div
        style={{
          padding: '14px 20px',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <h2
          style={{
            margin: 0,
            fontSize: '14px',
            fontWeight: 600,
            color: 'var(--text)',
          }}
        >
          {t('stats.planner.panel_title')}
        </h2>
      </div>

      {/* Contenido */}
      <div style={{ padding: '16px 20px' }}>

        {/* TimerSelector — siempre visible (P1), deshabilitado si no hay datos */}
        <TimerSelector
          value={timerMin}
          onChange={onTimerChange}
          disabled={isEmpty}
          t={t}
        />

        {loading && <PlannerSkeleton />}

        {!loading && error && (
          <ErrorBanner message={error} onRetry={onRetry} t={t} />
        )}

        {isEmpty && (
          <EmptyState onGoToIngest={onGoToIngest} t={t} />
        )}

        {hasData && (
          <>
            {buildPlayerMap(data.oasis).map(([rawPlayer, villageEntries]) => {
              // Localizar "Desconocido" → clave i18n; el resto se muestra tal cual
              const displayPlayer =
                rawPlayer === UNKNOWN_RAW
                  ? t('stats.planner.player_unknown')
                  : rawPlayer

              return (
                <PlayerOasisSection
                  key={rawPlayer}
                  playerName={displayPlayer}
                  rawName={rawPlayer}
                  villageCount={villageEntries.length}
                  t={t}
                >
                  {villageEntries.map(([rawVillage, oasisList]) => {
                    const displayVillage =
                      rawVillage === UNKNOWN_RAW
                        ? t('stats.planner.city_unknown')
                        : rawVillage

                    return (
                      <CityOasisSection
                        key={rawVillage}
                        cityName={displayVillage}
                        rawName={`${rawPlayer}-${rawVillage}`}
                        oasisList={oasisList}
                        t={t}
                      >
                        {oasisList.map((oasis) => (
                          <OasisBlock
                            key={`${rawPlayer}-${rawVillage}-${oasis.coord_x_dest}-${oasis.coord_y_dest}`}
                            oasis={oasis}
                            t={t}
                          />
                        ))}
                      </CityOasisSection>
                    )
                  })}
                </PlayerOasisSection>
              )
            })}

            {/* Nota anomalías excluidas de la fila Peor */}
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
                marginTop: '4px',
              }}
            >
              <span aria-hidden="true" style={{ color: 'var(--info)', fontSize: '13px', flexShrink: 0 }}>
                ⓘ
              </span>
              <span>{t('stats.planner.anomaly_note')}</span>
            </div>
          </>
        )}

      </div>
    </div>
  )
}
