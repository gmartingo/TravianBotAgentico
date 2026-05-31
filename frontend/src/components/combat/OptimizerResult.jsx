/**
 * OptimizerResult — Panel de resultados del optimizador de combate.
 *
 * Muestra un ranking de las N mejores alternativas (siempre — ganadoras o no).
 * Clic en una fila → expande el detalle inline con los datos por-alternativa.
 *
 * Props:
 *   result     — respuesta de POST /combat/optimize (o null). Ver OptimizeResponse
 *                en adapters/api/routes/combat.py.
 *   troopMeta  — [{ ordinal, name, iconUrl? }] tropas del atacante
 *
 * Comportamiento UX clave: si has_winning_combination=false pero alternatives no
 * está vacío, se pinta igualmente la tabla con las mejores alternativas no-ganadoras,
 * y el banner avisa de que ninguna gana para que el usuario decida.
 */
import { useState } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { TravianReport, ResIcon } from './TravianReport.jsx'

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(n, lang = 'es') {
  if (n == null || isNaN(n)) return '—'
  return new Intl.NumberFormat(lang).format(Math.round(n))
}

function ResourceLine({ resources, lang }) {
  if (!resources || typeof resources !== 'object') return <span style={{ color: 'var(--text-tertiary)' }}>—</span>
  const entries = Object.entries(resources).filter(([k, v]) => k !== 'total' && v > 0)
  if (entries.length === 0) return <span style={{ color: 'var(--text-tertiary)' }}>—</span>
  return (
    <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: '5px', alignItems: 'center' }}>
      {entries.map(([key, val]) => (
        <span key={key} style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', fontSize: '12px' }}>
          <ResIcon res={key} size={14} />
          <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
            {fmt(val, lang)}
          </span>
        </span>
      ))}
    </span>
  )
}

// Muestra iconos de tropas enviadas con bajas por tipo: 🗡 200 −15  ⚔ 50 −0 ...
// troopsSent llega como list[TroopResultResponse] (quantity_initial = enviadas,
// quantity_lost = bajas por tipo). Mostrar las bajas por-tropa es lo que el
// usuario pidió ("a parte de cuánto pierdo, qué tropas pierdo") sin tener que
// expandir el detalle.
function TroopsSentLine({ troopsSent, troopMeta, lang }) {
  const sent = (troopsSent ?? []).filter(t => (t.quantity_initial ?? 0) > 0)
  if (sent.length === 0) return <span style={{ color: 'var(--text-tertiary)' }}>—</span>

  const metaMap = {}
  for (const m of (troopMeta ?? [])) metaMap[m.ordinal] = m

  return (
    <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
      {sent.map(t => {
        const meta = metaMap[t.ordinal]
        const lost = t.quantity_lost ?? 0
        return (
          <span key={t.ordinal} style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', fontSize: '12px' }}>
            {meta?.iconUrl ? (
              <img src={meta.iconUrl} alt="" style={{ width: '16px', height: '16px', objectFit: 'contain', imageRendering: 'pixelated' }} />
            ) : (
              <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>T{t.ordinal}</span>
            )}
            <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', color: 'var(--text)' }}>
              {fmt(t.quantity_initial, lang)}
            </span>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontVariantNumeric: 'tabular-nums',
              fontSize: '11px',
              color: lost > 0 ? 'var(--danger)' : 'var(--text-tertiary)',
              fontWeight: lost > 0 ? 600 : 400,
            }}>
              {lost > 0 ? `−${fmt(lost, lang)}` : '0'}
            </span>
          </span>
        )
      })}
    </span>
  )
}

// Tabla genérica de tropas (sent/lost/survived) reutilizada para atacante y defensor
// dentro del detalle expandido. Mismo estilo que la del simulador.
function TroopsTable({ title, troops, troopMeta, lang, t, footnote }) {
  if (!troops || troops.length === 0) return null

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

  // troopMeta puede venir como array (atacante) o vacío (defensor: usamos icon_url del propio resultado)
  const metaMap = {}
  for (const m of (troopMeta ?? [])) metaMap[m.ordinal] = m

  function resolveIconUrl(iconUrl) {
    if (!iconUrl) return null
    if (iconUrl.startsWith('http')) return iconUrl
    return `/api${iconUrl}`
  }

  return (
    <div>
      <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: '4px' }}>
        {title}
      </div>
      <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '300px' }}>
          <thead>
            <tr>
              <th style={{ ...thStyle, textAlign: 'start' }}>{t('calc.result.col.troop')}</th>
              <th style={thStyle}>{t('calc.result.col.sent')}</th>
              <th style={thStyle}>{t('calc.result.col.losses')}</th>
              <th style={thStyle}>{t('calc.result.col.survived')}</th>
            </tr>
          </thead>
          <tbody>
            {troops.map((tr, idx) => {
              const meta = metaMap[tr.ordinal]
              // El defensor trae icon_url propio en la respuesta; el atacante usa troopMeta
              const iconUrl = meta?.iconUrl ?? resolveIconUrl(tr.icon_url)
              const sent = tr.quantity_initial ?? 0
              const survived = tr.quantity_survived ?? 0
              const losses = tr.quantity_lost ?? (sent - survived)
              return (
                <tr key={`${tr.tribe ?? ''}_${tr.ordinal}_${idx}`}
                  style={{ background: idx % 2 === 0 ? 'var(--surface)' : 'transparent' }}>
                  <td style={{ ...tdStyle, textAlign: 'start', fontFamily: 'inherit' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      {iconUrl
                        ? <img src={iconUrl} alt="" style={{ width: '16px', height: '16px', objectFit: 'contain', imageRendering: 'pixelated', flexShrink: 0 }} />
                        : <span style={{ width: '16px', fontSize: '10px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>T{tr.ordinal}</span>
                      }
                      <span style={{ fontSize: '12px' }}>{meta?.name ?? tr.name ?? `T${tr.ordinal}`}</span>
                    </div>
                  </td>
                  <td style={tdStyle}>{fmt(sent, lang)}</td>
                  <td style={{ ...tdStyle, color: losses > 0 ? 'var(--danger)' : 'var(--text-tertiary)' }}>
                    {losses > 0 ? `−${fmt(losses, lang)}` : '0'}
                  </td>
                  <td style={{ ...tdStyle, color: survived > 0 ? 'var(--success)' : 'var(--text-tertiary)', fontWeight: 600 }}>
                    {fmt(survived, lang)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {footnote && (
        <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '3px', fontStyle: 'italic' }}>
          {footnote}
        </div>
      )}
    </div>
  )
}

// ── Bloque Multi-Raid (solo Modo C) ──────────────────────────────────────────

function MultiRaidBlock({ alternative, troopMeta, lang, t }) {
  const { raids_possible, remaining_troops, aggregate } = alternative
  if (raids_possible == null) return null

  // Mapa de metadatos de tropas atacantes para iconos
  const metaMap = {}
  for (const m of (troopMeta ?? [])) metaMap[m.ordinal] = m

  function resolveIconUrl(iconUrl) {
    if (!iconUrl) return null
    if (iconUrl.startsWith('http')) return iconUrl
    return `/api${iconUrl}`
  }

  const thStyle = {
    padding: '4px 8px',
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
    padding: '4px 8px',
    fontSize: '12px',
    fontFamily: 'var(--font-mono)',
    fontVariantNumeric: 'tabular-nums',
    color: 'var(--text)',
    textAlign: 'end',
    borderBottom: '1px solid var(--border)',
  }

  return (
    <div style={{
      marginTop: '10px',
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
      padding: '10px 12px',
      background: 'var(--accent-subtle)',
      border: '1px solid var(--accent)',
      borderRadius: 'var(--radius-sm)',
    }}>
      {/* Línea destacada: "Puedes hacer esto N veces" */}
      <div style={{
        fontSize: '14px',
        fontWeight: 700,
        color: 'var(--accent-text)',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
      }}>
        <span>⟳</span>
        <span>
          {t('calc.optimizer.multiRaid.raidsPossible', { n: raids_possible })}
        </span>
      </div>

      {/* Tabla sobrantes */}
      {remaining_troops && remaining_troops.length > 0 && (
        <div>
          <div style={{
            fontSize: '11px',
            fontWeight: 600,
            color: 'var(--text-secondary)',
            textTransform: 'uppercase',
            letterSpacing: '.04em',
            marginBottom: '4px',
          }}>
            {t('calc.optimizer.multiRaid.remaining')}
          </div>
          <div style={{
            overflowX: 'auto',
            WebkitOverflowScrolling: 'touch',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)',
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '260px' }}>
              <thead>
                <tr>
                  <th style={{ ...thStyle, textAlign: 'start' }}>{t('calc.result.col.troop')}</th>
                  <th style={thStyle}>{t('calc.result.col.survived')}</th>
                  <th style={thStyle}>%</th>
                </tr>
              </thead>
              <tbody>
                {remaining_troops.map((tr, idx) => {
                  const meta = metaMap[tr.ordinal]
                  const iconUrl = meta?.iconUrl ?? resolveIconUrl(tr.icon_url)
                  const pct = tr.quantity_initial > 0
                    ? Math.round((tr.quantity_survived / tr.quantity_initial) * 100)
                    : 0
                  return (
                    <tr key={`${tr.ordinal}_${idx}`}
                      style={{ background: idx % 2 === 0 ? 'var(--surface)' : 'transparent' }}>
                      <td style={{ ...tdStyle, textAlign: 'start', fontFamily: 'inherit' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                          {iconUrl
                            ? <img src={iconUrl} alt="" style={{ width: '16px', height: '16px', objectFit: 'contain', imageRendering: 'pixelated', flexShrink: 0 }} />
                            : <span style={{ width: '16px', fontSize: '10px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>T{tr.ordinal}</span>
                          }
                          <span style={{ fontSize: '12px' }}>{meta?.name ?? tr.name ?? `T${tr.ordinal}`}</span>
                        </div>
                      </td>
                      <td style={{ ...tdStyle, color: tr.quantity_survived > 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                        {fmt(tr.quantity_survived, lang)}
                      </td>
                      <td style={{ ...tdStyle, color: 'var(--text-secondary)', fontSize: '11px' }}>
                        {pct}%
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Cuadro agregado */}
      {aggregate && (
        <div>
          <div style={{
            fontSize: '11px',
            fontWeight: 600,
            color: 'var(--text-secondary)',
            textTransform: 'uppercase',
            letterSpacing: '.04em',
            marginBottom: '4px',
          }}>
            {t('calc.optimizer.multiRaid.aggregate', { n: aggregate.n_raids })}
          </div>
          <div style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '12px',
            padding: '8px 10px',
            background: 'var(--surface-2)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)',
            fontSize: '12px',
          }}>
            {/* Recursos totales ganados */}
            {aggregate.total_resources_gained && aggregate.total_resources_gained.total > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <ResourceLine resources={aggregate.total_resources_gained} lang={lang} />
              </div>
            )}
            {/* Bajas totales en recursos */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--danger)' }}>
              <span style={{ fontWeight: 500 }}>−</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                {fmt(aggregate.total_resource_losses, lang)} R
              </span>
            </div>
            {/* Tropas totales enviadas */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--text-secondary)' }}>
              <span>⚔</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
                {fmt(aggregate.total_troops_sent, lang)}
              </span>
            </div>
            {/* Tiempo total (si hay) */}
            {aggregate.total_travel_time_h != null && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--text-secondary)' }}>
                <span>⏱</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
                  {Number(aggregate.total_travel_time_h).toFixed(2)} h
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}


// ── Panel de detalle inline (datos por-alternativa) ──────────────────────────

function DetailPanel({ alternative, defenderTroops, troopMeta, natureTroops, lang, t, inputMode }) {
  if (!alternative) {
    return (
      <div style={{ padding: '12px 16px', fontSize: '12px', color: 'var(--text-tertiary)' }}>
        {t('calc.optimizer.noDetail')}
      </div>
    )
  }

  // Normalizar attackerTroops para que TravianReport vea icon_url, name, etc.
  // troopMeta es el array [{ ordinal, name, iconUrl }] del atacante;
  // alternative.troops_sent ya trae icon_url pero a veces no name traducido.
  const metaMap = {}
  for (const m of (troopMeta ?? [])) metaMap[m.ordinal] = m
  const enrichedAtk = (alternative.troops_sent ?? []).map(t => {
    const meta = metaMap[t.ordinal]
    return {
      ordinal: t.ordinal,
      name: t.name ?? meta?.name ?? `T${t.ordinal}`,
      icon_url: t.icon_url ?? (meta?.iconUrl
        ? meta.iconUrl.replace(/^\/api/, '') // TravianReport vuelve a anteponer /api
        : null),
      quantity_initial: t.quantity_initial ?? 0,
      quantity_lost: t.quantity_lost ?? 0,
      quantity_survived: t.quantity_survived ?? 0,
    }
  })

  return (
    <div style={{
      padding: '12px 16px',
      background: 'var(--surface-2)',
      borderTop: '1px solid var(--border)',
    }}>
      <TravianReport
        attackerWins={!!alternative.is_winning}
        ratio={alternative.ratio}
        attackerPower={alternative.attacker_power}
        defenderPower={alternative.defender_power}
        attackerInfantryPower={alternative.attacker_infantry_power}
        attackerCavalryPower={alternative.attacker_cavalry_power}
        defenderInfantryPower={alternative.defender_infantry_power}
        defenderCavalryPower={alternative.defender_cavalry_power}
        attackerTroops={enrichedAtk}
        defenderTroops={defenderTroops ?? []}
        attackerTribeTroops={troopMeta}
        defenderTribeTroops={natureTroops}
        animalLoot={alternative.resources_gained ?? null}
        attackerCostLoss={alternative.resource_losses_breakdown ?? null}
        raidsCount={inputMode === 'C' ? alternative.raids_possible : null}
      />

      {/* Tiempo de marcha (no encaja en el report, lo dejamos como anotación) */}
      {alternative.travel_time_h != null && (
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)',
          display: 'flex', gap: '6px', alignItems: 'center', marginTop: '10px' }}>
          <span aria-hidden="true">⏱</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
            {Number(alternative.travel_time_h).toFixed(2)} h
          </span>
        </div>
      )}

      {/* Nota del defensor compartido entre alternativas (snapshot del mejor combate) */}
      {alternative.rank > 1 && (defenderTroops?.length ?? 0) > 0 && (
        <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '6px', fontStyle: 'italic' }}>
          {t('calc.optimizer.defenderNote')}
        </div>
      )}

      {/* Multi-raid block (totales agregados N raids) — solo en Modo C */}
      {inputMode === 'C' && alternative.raids_possible != null && (
        <div style={{ marginTop: '14px' }}>
          <MultiRaidBlock
            alternative={alternative}
            troopMeta={troopMeta}
            lang={lang}
            t={t}
          />
        </div>
      )}
    </div>
  )
}

// ── OptimizerResult ────────────────────────────────────────────────────────────

export function OptimizerResult({ result, troopMeta, natureTroops, inputMode = 'A' }) {
  const { t, lang } = useI18n()
  const [expandedRank, setExpandedRank] = useState(null)

  if (!result) return null

  const alternatives = result.alternatives ?? []
  const hasAlternatives = alternatives.length > 0
  const hasWinning = !!result.has_winning_combination

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
        {hasWinning ? (
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '6px',
            padding: '4px 12px',
            borderRadius: 'var(--radius-full)',
            background: 'rgba(36,138,61,.10)',
            border: '1px solid var(--success)',
          }}>
            <span style={{ fontSize: '13px' }}>✓</span>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--success)' }}>
              {t('calc.optimizer.result.found', { n: alternatives.length })}
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
        {result.message && (
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            {result.message}
          </span>
        )}
      </div>

      {/* ── Tabla de ranking ── */}
      {/* Se pinta SIEMPRE que haya alternatives, aunque ninguna gane.
          Columnas:
            # | tropas enviadas (chips) | pérdidas (R) | saqueo (R) | NETO (R) | (Modo C: N raids)
          Click en una fila → expande con el informe Travian completo. */}
      {hasAlternatives && (
        <div>
          {/* Cabecera de la tabla — añadimos columna NETO (siempre) y N raids (solo Modo C) */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: inputMode === 'C'
              ? '36px 1fr auto auto auto auto'
              : '36px 1fr auto auto auto',
            gap: '10px',
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
            <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em', textAlign: 'end', minWidth: '60px' }}>
              {t('calc.optimizer.result.col.net')}
            </span>
            {inputMode === 'C' && (
              <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em', textAlign: 'end', minWidth: '52px' }}>
                {t('calc.optimizer.result.col.raids')}
              </span>
            )}
          </div>

          {/* Filas */}
          {alternatives.map((combo, idx) => {
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
                    gridTemplateColumns: inputMode === 'C'
                      ? '36px 1fr auto auto auto auto'
                      : '36px 1fr auto auto auto',
                    gap: '10px',
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
                  {/* Rango con marca visual de ganadora / no-ganadora */}
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                    fontSize: '13px',
                    fontWeight: 700,
                    color: isExpanded
                      ? 'var(--accent-text)'
                      : (combo.is_winning ? 'var(--success)' : 'var(--danger)'),
                  }}
                    title={combo.is_winning ? t('calc.result.attackerWins') : t('calc.result.defenderWins')}
                  >
                    {combo.is_winning ? '✓' : '✗'} {combo.rank ?? idx + 1}
                  </span>

                  {/* Tropas enviadas */}
                  <TroopsSentLine troopsSent={combo.troops_sent} troopMeta={troopMeta} lang={lang} />

                  {/* Bajas en recursos (coste tropas perdidas) */}
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontVariantNumeric: 'tabular-nums',
                    fontSize: '12px',
                    color: combo.total_resource_losses > 0 ? 'var(--danger)' : 'var(--text-tertiary)',
                    textAlign: 'end',
                    whiteSpace: 'nowrap',
                  }}>
                    {combo.total_resource_losses != null ? `−${fmt(combo.total_resource_losses, lang)} R` : '—'}
                  </span>

                  {/* Recursos ganados (botín animal) */}
                  <span style={{ textAlign: 'end', minWidth: '80px' }}>
                    <ResourceLine resources={combo.resources_gained} lang={lang} />
                  </span>

                  {/* Neto = botín − coste */}
                  {(() => {
                    const loot = combo.resources_gained?.total ?? 0
                    const cost = combo.total_resource_losses ?? 0
                    const net = loot - cost
                    const color = net > 0 ? 'var(--success)' : net < 0 ? 'var(--danger)' : 'var(--text-tertiary)'
                    return (
                      <span style={{
                        fontFamily: 'var(--font-mono)',
                        fontVariantNumeric: 'tabular-nums',
                        fontSize: '12px',
                        fontWeight: 700,
                        color,
                        textAlign: 'end',
                        whiteSpace: 'nowrap',
                        minWidth: '60px',
                      }}>
                        {net === 0 ? '0' : (net > 0 ? '+' : '−') + fmt(Math.abs(net), lang)}
                      </span>
                    )
                  })()}

                  {/* N raids (solo en Modo C) */}
                  {inputMode === 'C' && (
                    <span style={{
                      fontFamily: 'var(--font-mono)',
                      fontVariantNumeric: 'tabular-nums',
                      fontSize: '13px',
                      fontWeight: 700,
                      color: 'var(--accent-text)',
                      textAlign: 'end',
                      whiteSpace: 'nowrap',
                      minWidth: '52px',
                    }} title={t('calc.optimizer.result.col.raids')}>
                      {combo.raids_possible != null ? `×${fmt(combo.raids_possible, lang)}` : '—'}
                    </span>
                  )}
                </div>

                {/* Detalle inline expandido */}
                {isExpanded && (
                  <DetailPanel
                    alternative={combo}
                    defenderTroops={result.defender_troops}
                    troopMeta={troopMeta}
                    natureTroops={natureTroops}
                    lang={lang}
                    t={t}
                    inputMode={inputMode}
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
