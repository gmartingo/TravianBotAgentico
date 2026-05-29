/**
 * CombatResult — Panel de resultado del simulador de combate.
 *
 * Props:
 *   result  — respuesta directa de POST /combat/simulate (o null si aún no hay resultado)
 *
 * Estructura real de la respuesta:
 *   attacker_wins, ratio, attacker_power, defender_power,
 *   attacker_troops[{ tribe, ordinal, name, icon_url, quantity_initial, quantity_survived, quantity_lost }],
 *   defender_troops[...], loot{ capacity, potential, resources_gained_from_animals },
 *   resource_losses{ attacker{ total_resources, breakdown }, defender{ total_resources } }, warnings[]
 */
import { useI18n } from '../../i18n/index.jsx'

function fmt(n, lang = 'es') {
  if (n == null || isNaN(n)) return '—'
  return new Intl.NumberFormat(lang).format(Math.round(n))
}

const RES_ICONS = { wood: '🪵', clay: '🧱', iron: '⚙️', crop: '🌾' }

function ResourceRow({ resources, lang }) {
  if (!resources || typeof resources !== 'object') return null
  const entries = Object.entries(resources).filter(([k, v]) => k !== 'total' && v > 0)
  if (entries.length === 0) return null
  return (
    <span style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
      {entries.map(([key, val]) => (
        <span key={key} style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '13px' }}>
          <span>{RES_ICONS[key] ?? key}</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
            {fmt(val, lang)}
          </span>
        </span>
      ))}
    </span>
  )
}

// icon_url del backend es relativa (/static/icons/...) — Vite proxia /api → backend
function resolveIconUrl(icon_url) {
  if (!icon_url) return null
  if (icon_url.startsWith('http')) return icon_url
  return `/api${icon_url}`
}

// ── Tabla de tropas (usa campos directos de la respuesta API) ─────────────────

function TroopsTable({ title, troops, lang, t }) {
  if (!troops || troops.length === 0) return null

  const thStyle = {
    padding: '6px 8px',
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
  const thStartStyle = { ...thStyle, textAlign: 'start' }
  const tdBase = {
    padding: '6px 8px',
    fontSize: '13px',
    fontFamily: 'var(--font-mono)',
    fontVariantNumeric: 'tabular-nums',
    borderBottom: '1px solid var(--border)',
    textAlign: 'end',
  }

  return (
    <div style={{ marginBottom: '12px' }}>
      <div style={{
        fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)',
        marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '.04em',
      }}>
        {title}
      </div>
      <div style={{
        overflowX: 'auto', WebkitOverflowScrolling: 'touch',
        borderRadius: 'var(--radius-md)', border: '1px solid var(--border)',
      }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '360px' }}>
          <thead>
            <tr>
              <th style={thStartStyle}>{t('calc.result.col.troop')}</th>
              <th style={thStyle}>{t('calc.result.col.sent')}</th>
              <th style={thStyle}>{t('calc.result.col.losses')}</th>
              <th style={thStyle}>{t('calc.result.col.survived')}</th>
            </tr>
          </thead>
          <tbody>
            {troops.map((tr, idx) => (
              <tr key={`${tr.tribe}_${tr.ordinal}_${idx}`}
                style={{ background: idx % 2 === 0 ? 'var(--surface)' : 'transparent' }}>
                <td style={{ ...tdBase, textAlign: 'start', fontFamily: 'inherit' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {resolveIconUrl(tr.icon_url) ? (
                      <img
                        src={resolveIconUrl(tr.icon_url)}
                        alt=""
                        style={{ width: '20px', height: '20px', objectFit: 'contain', imageRendering: 'pixelated', flexShrink: 0 }}
                      />
                    ) : (
                      <span style={{ width: '20px', fontSize: '11px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                        T{tr.ordinal}
                      </span>
                    )}
                    <span style={{ fontSize: '13px', color: 'var(--text)' }}>
                      {tr.name ?? `T${tr.ordinal}`}
                    </span>
                  </div>
                </td>
                <td style={{ ...tdBase, color: 'var(--text)' }}>
                  {fmt(tr.quantity_initial, lang)}
                </td>
                <td style={{ ...tdBase, color: (tr.quantity_lost ?? 0) > 0 ? 'var(--danger)' : 'var(--text-tertiary)' }}>
                  {(tr.quantity_lost ?? 0) > 0 ? `−${fmt(tr.quantity_lost, lang)}` : '0'}
                </td>
                <td style={{ ...tdBase, color: (tr.quantity_survived ?? 0) > 0 ? 'var(--success)' : 'var(--text-tertiary)', fontWeight: 600 }}>
                  {fmt(tr.quantity_survived, lang)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── CombatResult ───────────────────────────────────────────────────────────────

export function CombatResult({ result }) {
  const { t, lang } = useI18n()

  if (!result) return null

  const attackerWins = result.attacker_wins === true

  return (
    <div
      role="region"
      aria-label={t('calc.result.title')}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '16px',
        marginTop: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
      }}
    >
      {/* ── Cabecera: ganador + fuerzas de combate ── */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12px' }}>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px',
          padding: '5px 14px',
          borderRadius: 'var(--radius-full)',
          background: attackerWins ? 'rgba(36,138,61,.12)' : 'rgba(201,53,44,.12)',
          border: `1px solid ${attackerWins ? 'var(--success)' : 'var(--danger)'}`,
        }}>
          <span style={{ fontSize: '15px' }}>{attackerWins ? '⚔' : '🛡'}</span>
          <span style={{
            fontSize: '14px', fontWeight: 600,
            color: attackerWins ? 'var(--success)' : 'var(--danger)',
          }}>
            {attackerWins ? t('calc.result.attackerWins') : t('calc.result.defenderWins')}
          </span>
        </div>

        {result.ratio != null && (
          <span style={{ fontSize: '13px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
            {t('calc.result.ratio', { ratio: Number(result.ratio).toFixed(2) })}
          </span>
        )}

        {/* Fuerzas de combate */}
        {(result.attacker_power != null || result.defender_power != null) && (
          <div style={{ display: 'flex', gap: '16px', marginLeft: 'auto', flexWrap: 'wrap' }}>
            {result.attacker_power != null && (
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                ⚔ <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                  {fmt(result.attacker_power, lang)}
                </span>
              </span>
            )}
            {result.defender_power != null && (
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                🛡 <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                  {fmt(result.defender_power, lang)}
                </span>
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── Tabla atacante ── */}
      <TroopsTable
        title={t('calc.result.attacker')}
        troops={result.attacker_troops}
        lang={lang}
        t={t}
      />

      {/* ── Tabla defensor ── */}
      <TroopsTable
        title={t('calc.result.defender')}
        troops={result.defender_troops}
        lang={lang}
        t={t}
      />

      {/* ── Botín ── */}
      {result.loot && (
        <div style={{
          padding: '10px 12px',
          background: 'var(--surface-2)',
          borderRadius: 'var(--radius-sm)',
          display: 'flex', flexDirection: 'column', gap: '6px',
        }}>
          <div style={{
            fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)',
            textTransform: 'uppercase', letterSpacing: '.04em',
          }}>
            {t('calc.result.loot.title')}
          </div>
          {result.loot.capacity != null && (
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)', display: 'flex', gap: '6px', alignItems: 'center' }}>
              <span>{t('calc.result.loot.capacity')}:</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', color: 'var(--text)' }}>
                {fmt(result.loot.capacity, lang)}
              </span>
            </div>
          )}
          {result.loot.resources_gained_from_animals && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center', fontSize: '13px', color: 'var(--text-secondary)' }}>
              <span>{t('calc.result.loot.animals')}:</span>
              <ResourceRow resources={result.loot.resources_gained_from_animals} lang={lang} />
              {result.loot.resources_gained_from_animals.total != null && (
                <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', color: 'var(--text)', fontWeight: 600 }}>
                  ({fmt(result.loot.resources_gained_from_animals.total, lang)} total)
                </span>
              )}
            </div>
          )}
          {result.loot.potential && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center', fontSize: '13px', color: 'var(--text-secondary)' }}>
              <span>{t('calc.result.loot.potential')}:</span>
              <ResourceRow resources={result.loot.potential} lang={lang} />
            </div>
          )}
        </div>
      )}

      {/* ── Pérdidas en recursos ── */}
      {result.resource_losses && (
        <div style={{
          padding: '10px 12px',
          background: 'var(--surface-2)',
          borderRadius: 'var(--radius-sm)',
          display: 'flex', flexDirection: 'column', gap: '6px',
        }}>
          <div style={{
            fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)',
            textTransform: 'uppercase', letterSpacing: '.04em',
          }}>
            {t('calc.result.losses.title')}
          </div>
          {result.resource_losses.attacker?.total_resources != null && (
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '13px', color: 'var(--text-secondary)' }}>
              <span>{t('calc.result.losses.attacker')}:</span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
                color: result.resource_losses.attacker.total_resources > 0 ? 'var(--danger)' : 'var(--text-tertiary)',
                fontWeight: 600,
              }}>
                {fmt(result.resource_losses.attacker.total_resources, lang)}
              </span>
            </div>
          )}
          {result.resource_losses.defender?.total_resources != null && (
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '13px', color: 'var(--text-secondary)' }}>
              <span>{t('calc.result.losses.defender')}:</span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
                color: result.resource_losses.defender.total_resources > 0 ? 'var(--danger)' : 'var(--text-tertiary)',
                fontWeight: 600,
              }}>
                {fmt(result.resource_losses.defender.total_resources, lang)}
              </span>
            </div>
          )}
        </div>
      )}

      {/* ── Warnings ── */}
      {result.warnings && result.warnings.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div style={{
            fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)',
            textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: '2px',
          }}>
            {t('calc.result.warnings')}
          </div>
          {result.warnings.map((w, i) => (
            <div key={i} style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              padding: '4px 10px',
              background: 'var(--accent-subtle)',
              color: 'var(--accent-text)',
              borderRadius: 'var(--radius-full)',
              fontSize: '12px',
            }}>
              <span aria-hidden="true">⚠</span>
              {typeof w === 'string' ? w : w.message ?? JSON.stringify(w)}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
