/**
 * OptimizerResult — Panel de resultados del optimizador de combate.
 *
 * Muestra un ranking de las N mejores combinaciones de tropas.
 * Clic en una fila → expande el detalle inline (resultado completo del simulador
 * para esa combinación, usando el mismo layout compacto que CombatResult).
 *
 * Props:
 *   result     — respuesta de POST /combat/optimize (o null)
 *   troopMeta  — [{ ordinal, name, iconUrl? }] tropas del atacante
 *
 * Estructura de la respuesta esperada:
 * {
 *   combinations: [
 *     {
 *       rank: 1,
 *       score: 0.87,
 *       troops_sent: [{ ordinal, quantity }],
 *       resource_losses: 6540,
 *       resources_gained: { wood, clay, iron, crop },
 *       simulation: { ...mismo shape que /simulate }  // opcional
 *     }
 *   ]
 * }
 *
 * Si result.combinations está vacío → muestra badge "sin combinación ganadora".
 */
import { useState } from 'react'
import { useI18n } from '../../i18n/index.jsx'

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(n, lang = 'es') {
  if (n == null || isNaN(n)) return '—'
  return new Intl.NumberFormat(lang).format(Math.round(n))
}

const RES_ICONS = { wood: '🪵', clay: '🧱', iron: '⚙', crop: '🌾' }

function ResourceLine({ resources, lang }) {
  if (!resources || typeof resources !== 'object') return <span style={{ color: 'var(--text-tertiary)' }}>—</span>
  const entries = Object.entries(resources).filter(([, v]) => v > 0)
  if (entries.length === 0) return <span style={{ color: 'var(--text-tertiary)' }}>—</span>
  return (
    <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: '5px', alignItems: 'center' }}>
      {entries.map(([key, val]) => (
        <span key={key} style={{ display: 'inline-flex', alignItems: 'center', gap: '2px', fontSize: '12px' }}>
          <span>{RES_ICONS[key] ?? key}</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
            {fmt(val, lang)}
          </span>
        </span>
      ))}
    </span>
  )
}

// Muestra iconos de tropas enviadas: 🗡×200 ⚔×50 ...
function TroopsSentLine({ troopsSent, troopMeta, lang }) {
  if (!troopsSent || troopsSent.length === 0) return <span style={{ color: 'var(--text-tertiary)' }}>—</span>

  const metaMap = {}
  for (const m of (troopMeta ?? [])) metaMap[m.ordinal] = m

  return (
    <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
      {troopsSent.map(t => {
        const meta = metaMap[t.ordinal]
        return (
          <span key={t.ordinal} style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', fontSize: '12px' }}>
            {meta?.iconUrl ? (
              <img src={meta.iconUrl} alt="" style={{ width: '16px', height: '16px', objectFit: 'contain', imageRendering: 'pixelated' }} />
            ) : (
              <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>T{t.ordinal}</span>
            )}
            <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', color: 'var(--text)' }}>
              ×{fmt(t.quantity, lang)}
            </span>
          </span>
        )
      })}
    </span>
  )
}

// ── Panel de detalle inline (versión compacta del resultado de simulación) ─────

function DetailPanel({ simulation, troopMeta, lang, t }) {
  if (!simulation) {
    return (
      <div style={{ padding: '12px 16px', fontSize: '12px', color: 'var(--text-tertiary)' }}>
        {t('calc.optimizer.noDetail')}
      </div>
    )
  }

  const attackerWins = simulation.winner === 'attacker'

  const thStyle = {
    padding: '5px 8px',
    fontSize: '11px',
    fontWeight: 500,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '.04em',
    textAlign: 'end',
    background: 'var(--surface-2)',
    borderBottom: '1px solid var(--border)',
    whiteSpace: 'nowrap',
  }
  const tdStyle = {
    padding: '5px 8px',
    fontSize: '12px',
    fontFamily: 'var(--font-mono)',
    fontVariantNumeric: 'tabular-nums',
    color: 'var(--text)',
    textAlign: 'end',
    borderBottom: '1px solid var(--border)',
  }

  const metaMap = {}
  for (const m of (troopMeta ?? [])) metaMap[m.ordinal] = m

  const atkTroops = simulation.attacker?.troops ?? []
  const defTroops = (simulation.defenders ?? [simulation.defender]).filter(Boolean).flatMap(d => d.troops ?? [])

  return (
    <div style={{
      padding: '12px 16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
      background: 'var(--surface-2)',
      borderTop: '1px solid var(--border)',
    }}>
      {/* Badge ganador */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: '5px',
          padding: '3px 10px',
          borderRadius: 'var(--radius-full)',
          background: attackerWins ? 'rgba(36,138,61,.10)' : 'rgba(201,53,44,.10)',
          border: `1px solid ${attackerWins ? 'var(--success)' : 'var(--danger)'}`,
        }}>
          <span style={{ fontSize: '13px' }}>{attackerWins ? '⚔' : '🛡'}</span>
          <span style={{ fontSize: '12px', fontWeight: 600, color: attackerWins ? 'var(--success)' : 'var(--danger)' }}>
            {attackerWins ? t('calc.result.attackerWins') : t('calc.result.defenderWins')}
          </span>
        </div>
        {simulation.combat_ratio != null && (
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
            {t('calc.result.ratio', { ratio: simulation.combat_ratio.toFixed(2) })}
          </span>
        )}
      </div>

      {/* Tabla compacta */}
      {atkTroops.length > 0 && (
        <div>
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: '4px' }}>
            {t('calc.result.attacker')}
          </div>
          <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '300px' }}>
              <thead>
                <tr>
                  <th style={{ ...thStyle, textAlign: 'start' }}>{t('calc.result.col.troop')}</th>
                  <th style={thStyle}>{t('calc.result.col.sent')}</th>
                  <th style={thStyle}>{t('calc.result.col.survived')}</th>
                  <th style={thStyle}>{t('calc.result.col.losses')}</th>
                </tr>
              </thead>
              <tbody>
                {atkTroops.map((tr, idx) => {
                  const meta = metaMap[tr.ordinal]
                  const losses = (tr.sent ?? 0) - (tr.survived ?? 0)
                  return (
                    <tr key={tr.ordinal ?? idx} style={{ background: idx % 2 === 0 ? 'var(--surface)' : 'transparent' }}>
                      <td style={{ ...tdStyle, textAlign: 'start', fontFamily: 'inherit' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                          {meta?.iconUrl
                            ? <img src={meta.iconUrl} alt="" style={{ width: '16px', height: '16px', objectFit: 'contain', imageRendering: 'pixelated', flexShrink: 0 }} />
                            : <span style={{ width: '16px', fontSize: '10px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>T{tr.ordinal}</span>
                          }
                          <span style={{ fontSize: '12px' }}>{meta?.name ?? tr.name ?? `T${tr.ordinal}`}</span>
                        </div>
                      </td>
                      <td style={tdStyle}>{fmt(tr.sent, lang)}</td>
                      <td style={{ ...tdStyle, color: (tr.survived ?? 0) > 0 ? 'var(--success)' : 'var(--text-tertiary)' }}>
                        {fmt(tr.survived, lang)}
                      </td>
                      <td style={{ ...tdStyle, color: losses > 0 ? 'var(--danger)' : 'var(--text-tertiary)' }}>
                        {fmt(losses, lang)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Botín */}
      {simulation.loot && (
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontWeight: 500 }}>{t('calc.result.loot.title')}:</span>
          <ResourceLine resources={simulation.loot.potential ?? simulation.loot.capacity} lang={lang} />
        </div>
      )}

      {/* Pérdidas atacante */}
      {simulation.attacker?.resource_losses != null && (
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'flex', gap: '6px', alignItems: 'center' }}>
          <span style={{ fontWeight: 500 }}>{t('calc.result.losses.attacker')}:</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', color: 'var(--danger)', fontWeight: 600 }}>
            {fmt(simulation.attacker.resource_losses, lang)}
          </span>
        </div>
      )}
    </div>
  )
}

// ── OptimizerResult ────────────────────────────────────────────────────────────

export function OptimizerResult({ result, troopMeta }) {
  const { t, lang } = useI18n()
  const [expandedRank, setExpandedRank] = useState(null)

  if (!result) return null

  const combinations = result.combinations ?? []
  const hasWinners = combinations.length > 0

  function toggleRow(rank) {
    setExpandedRank(prev => prev === rank ? null : rank)
  }

  return (
    <div
      role="region"
      aria-label={t('calc.optimizer.result.title')}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        marginTop: '16px',
      }}
    >
      {/* ── Cabecera: badge resumen ── */}
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--surface-2)',
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        flexWrap: 'wrap',
      }}>
        {hasWinners ? (
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '6px',
            padding: '4px 12px',
            borderRadius: 'var(--radius-full)',
            background: 'rgba(36,138,61,.10)',
            border: '1px solid var(--success)',
          }}>
            <span style={{ fontSize: '13px' }}>✓</span>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--success)' }}>
              {t('calc.optimizer.result.found', { n: combinations.length })}
            </span>
          </div>
        ) : (
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '6px',
            padding: '4px 12px',
            borderRadius: 'var(--radius-full)',
            background: 'var(--accent-subtle)',
            border: '1px solid var(--accent)',
          }}>
            <span style={{ fontSize: '13px' }} aria-hidden="true">⚠</span>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--accent-text)' }}>
              {t('calc.optimizer.result.noWinner')}
            </span>
          </div>
        )}
      </div>

      {/* ── Tabla de ranking ── */}
      {hasWinners && (
        <div>
          {/* Cabecera de la tabla */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '32px 1fr auto auto',
            gap: '8px',
            padding: '7px 14px',
            background: 'var(--surface-2)',
            borderBottom: '1px solid var(--border)',
          }}>
            <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em' }}>#</span>
            <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em' }}>
              {t('calc.optimizer.result.col.troops')}
            </span>
            <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em', textAlign: 'end' }}>
              {t('calc.optimizer.result.col.losses')}
            </span>
            <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em', textAlign: 'end', minWidth: '80px' }}>
              {t('calc.optimizer.result.col.gained')}
            </span>
          </div>

          {/* Filas */}
          {combinations.map((combo, idx) => {
            const isExpanded = expandedRank === combo.rank
            return (
              <div key={combo.rank ?? idx}>
                {/* Fila principal */}
                <div
                  role="button"
                  tabIndex={0}
                  aria-expanded={isExpanded}
                  onClick={() => toggleRow(combo.rank ?? idx)}
                  onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); toggleRow(combo.rank ?? idx) } }}
                  onFocus={e => { e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '-2px' }}
                  onBlur={e => { e.currentTarget.style.outline = 'none' }}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '32px 1fr auto auto',
                    gap: '8px',
                    padding: '9px 14px',
                    cursor: 'pointer',
                    background: isExpanded ? 'var(--accent-subtle)' : (idx % 2 === 0 ? 'var(--surface)' : 'transparent'),
                    borderBottom: '1px solid var(--border)',
                    alignItems: 'center',
                    transition: 'background var(--dur-fast) var(--ease)',
                    outline: 'none',
                  }}
                  onMouseEnter={e => { if (!isExpanded) e.currentTarget.style.background = 'var(--surface-2)' }}
                  onMouseLeave={e => { if (!isExpanded) e.currentTarget.style.background = idx % 2 === 0 ? 'var(--surface)' : 'transparent' }}
                >
                  {/* Rango */}
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                    fontSize: '13px',
                    fontWeight: 700,
                    color: isExpanded ? 'var(--accent-text)' : 'var(--text-secondary)',
                  }}>
                    {combo.rank ?? idx + 1}
                  </span>

                  {/* Tropas enviadas */}
                  <TroopsSentLine troopsSent={combo.troops_sent} troopMeta={troopMeta} lang={lang} />

                  {/* Bajas en recursos */}
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                    fontSize: '12px',
                    color: combo.resource_losses > 0 ? 'var(--danger)' : 'var(--text-tertiary)',
                    textAlign: 'end',
                    whiteSpace: 'nowrap',
                  }}>
                    {combo.resource_losses != null ? `${fmt(combo.resource_losses, lang)} R` : '—'}
                  </span>

                  {/* Recursos ganados */}
                  <span style={{ textAlign: 'end', minWidth: '80px' }}>
                    <ResourceLine resources={combo.resources_gained} lang={lang} />
                  </span>
                </div>

                {/* Detalle inline expandido */}
                {isExpanded && (
                  <DetailPanel
                    simulation={combo.simulation}
                    troopMeta={troopMeta}
                    lang={lang}
                    t={t}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
