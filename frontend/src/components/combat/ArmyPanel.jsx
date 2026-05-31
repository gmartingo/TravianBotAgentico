/**
 * ArmyPanel — Panel de ejército reutilizable (atacante / defensor / refuerzo).
 *
 * Props:
 *   role             — 'attacker' | 'defender' | 'reinforcement'
 *   panelId          — string único para aria-controls
 *   tribe            — string (tribeId actualmente seleccionado)
 *   availableTribes  — [{ id, labelKey?, labelText? }]
 *   onTribeChange    — (tribeId) => void
 *   troops           — [{ ordinal, name, iconUrl? }] (de la tribu)
 *   troopValues      — { [ordinal]: { qty, smithy } }
 *   onTroopChange    — (ordinal, field, value) => void
 *
 *   -- Solo atacante --
 *   attackType       — 'attack' | 'raid'
 *   onAttackTypeChange — (type) => void
 *   allianceBonusAtk — number (0-5)
 *   onAllianceBonusAtk — (n) => void
 *   artifactType     — 'none' | 'fast1_5' | 'fast2'
 *   onArtifactChange — (type) => void
 *
 *   -- Solo defensor --
 *   wallLevel        — number (0-20)
 *   onWallChange     — (n) => void
 *   stonemasonLevel  — number (0-5)
 *   onStonemasonChange — (n) => void
 *   allianceBonusDef — number (0-5)
 *   onAllianceBonusDef — (n) => void
 *
 *   -- Héroe (atacante y defensor) --
 *   heroPoints       — number
 *   onHeroPoints     — (n) => void
 *   heroBonusPct     — number
 *   onHeroBonusPct   — (n) => void
 *
 *   -- Refuerzo --
 *   reinforcementIndex — number (para mostrar "Refuerzo 1", "Refuerzo 2"…)
 *   onRemove           — () => void  (botón eliminar refuerzo)
 *
 * Accesibilidad:
 *   - El panel tiene role="region" con aria-labelledby
 *   - El botón colapsar tiene aria-expanded + aria-controls
 *   - Todos los inputs con aria-label
 */
import { useState, useId } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { TribeBar } from './TribeBar.jsx'
import { TroopGrid } from './TroopGrid.jsx'

// ── Iconos ────────────────────────────────────────────────────────────────────

function IconSword() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '16px', height: '16px', flexShrink: 0 }} aria-hidden="true">
      <polyline points="14.5 17.5 3 6 3 3 6 3 17.5 14.5" />
      <line x1="13" y1="19" x2="19" y2="13" />
      <line x1="16" y1="16" x2="20" y2="20" />
      <line x1="19" y1="21" x2="21" y2="19" />
    </svg>
  )
}

function IconShieldFill() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '16px', height: '16px', flexShrink: 0 }} aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

function IconUser() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '16px', height: '16px', flexShrink: 0 }} aria-hidden="true">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  )
}

function IconChevronDown({ size = 14, rotated = false }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round"
      style={{
        width: `${size}px`, height: `${size}px`, flexShrink: 0,
        transform: rotated ? 'rotate(180deg)' : 'none',
        transition: 'transform var(--dur-fast) var(--ease)',
      }}
      aria-hidden="true">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

function IconTrash() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '14px', height: '14px', flexShrink: 0 }} aria-hidden="true">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  )
}

// ── Sub-componentes ────────────────────────────────────────────────────────────

function RoleIcon({ role }) {
  if (role === 'attacker') return <IconSword />
  if (role === 'defender') return <IconShieldFill />
  return <IconUser />
}

function roleColor(role) {
  if (role === 'attacker') return 'var(--danger)'
  if (role === 'defender') return 'var(--info)'
  return 'var(--text-secondary)'
}

// Input numérico genérico compacto
function NumInput({ value, onChange, min = 0, max = 9999, placeholder = '0', ariaLabel, width = 48 }) {
  return (
    <input
      type="text"
      inputMode="numeric"
      pattern="[0-9]*"
      value={value === 0 ? '' : value}
      placeholder={placeholder}
      aria-label={ariaLabel}
      onChange={e => {
        const raw = e.target.value.replace(/\D/g, '')
        const n = raw === '' ? 0 : Math.min(max, Math.max(min, Number(raw)))
        onChange(n)
      }}
      onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
      onBlur={e => { e.currentTarget.style.borderColor = 'var(--border-strong)' }}
      style={{
        width: `${width}px`,
        height: '26px',
        padding: '0 4px',
        background: 'var(--surface-2)',
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '13px',
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
        color: 'var(--text)',
        textAlign: 'center',
        outline: 'none',
        transition: 'border-color var(--dur-fast) var(--ease)',
        boxSizing: 'border-box',
      }}
    />
  )
}

// Toggle pill Attack / Raid
function AttackTypeToggle({ value, onChange }) {
  const { t } = useI18n()
  const types = ['raid', 'attack']
  return (
    <div role="radiogroup" aria-label={t('calc.attackType.attack')}
      style={{ display: 'flex', borderRadius: 'var(--radius-sm)', overflow: 'hidden', border: '1px solid var(--border-strong)' }}>
      {types.map(type => {
        const isActive = value === type
        return (
          <button
            key={type}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => onChange(type)}
            style={{
              height: '26px',
              padding: '0 10px',
              border: 'none',
              background: isActive ? 'var(--btn-primary-bg)' : 'var(--surface-2)',
              color: isActive ? 'var(--btn-primary-text)' : 'var(--text-secondary)',
              fontSize: '12px',
              fontWeight: isActive ? 600 : 400,
              cursor: 'pointer',
              fontFamily: 'inherit',
              transition: 'background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease)',
            }}
          >
            {t(`calc.attackType.${type}`)}
          </button>
        )
      })}
    </div>
  )
}

// Select de bonus % alianza (0-5)
function AllianceBonusSelect({ value, onChange, ariaLabel }) {
  return (
    <select
      value={value}
      onChange={e => onChange(Number(e.target.value))}
      aria-label={ariaLabel}
      style={{
        height: '26px',
        padding: '0 6px',
        background: 'var(--surface-2)',
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '12px',
        color: 'var(--text)',
        cursor: 'pointer',
        fontFamily: 'inherit',
        outline: 'none',
      }}
    >
      {[0, 1, 2, 3, 4, 5].map(n => (
        <option key={n} value={n}>{n}%</option>
      ))}
    </select>
  )
}

// Select de artefacto (velocidad)
function ArtifactSelect({ value, onChange }) {
  const { t } = useI18n()
  const options = [
    { id: 'none', label: t('calc.artifact.none') },
    { id: 'fast1_5', label: t('calc.artifact.fast1_5') },
    { id: 'fast2', label: t('calc.artifact.fast2') },
  ]
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      aria-label={t('calc.artifact')}
      style={{
        height: '26px',
        padding: '0 6px',
        background: 'var(--surface-2)',
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '12px',
        color: 'var(--text)',
        cursor: 'pointer',
        fontFamily: 'inherit',
        outline: 'none',
      }}
    >
      {options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
    </select>
  )
}

// ── ArmyPanel ─────────────────────────────────────────────────────────────────

export function ArmyPanel({
  role,
  panelId,
  // Tribe
  tribe,
  availableTribes,
  onTribeChange,
  // Troops
  troops,
  troopValues,
  onTroopChange,
  // Attacker controls
  attackType = 'raid',
  onAttackTypeChange,
  allianceBonusAtk = 0,
  onAllianceBonusAtk,
  artifactType = 'none',
  onArtifactChange,
  // Defender controls
  wallLevel = 0,
  onWallChange,
  stonemasonLevel = 0,
  onStonemasonChange,
  allianceBonusDef = 0,
  onAllianceBonusDef,
  // Hero (atacante y defensor)
  heroPoints = 0,
  onHeroPoints,
  heroBonusPct = 0,
  onHeroBonusPct,
  // Reinforcement
  reinforcementIndex,
  onRemove,
}) {
  const { t } = useI18n()
  const headingId = `${panelId}-heading`
  const bodyId = `${panelId}-body`
  const heroId = `${panelId}-hero`

  const [collapsed, setCollapsed] = useState(false)
  const [heroExpanded, setHeroExpanded] = useState(false)

  const isAttacker = role === 'attacker'
  const isDefender = role === 'defender'
  const isReinforcement = role === 'reinforcement'

  function getRoleLabel() {
    if (isReinforcement) {
      return `${t('calc.reinforcement')} ${reinforcementIndex ?? ''}`
    }
    return isAttacker ? t('calc.attacker') : t('calc.defender')
  }

  const roleLabel = getRoleLabel()

  return (
    <section
      role="region"
      aria-labelledby={headingId}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        marginBottom: '8px',
      }}
    >
      {/* ── Header ── */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '10px 14px',
        borderBottom: collapsed ? 'none' : '1px solid var(--border)',
        background: 'var(--surface-2)',
      }}>
        <span style={{ color: roleColor(role), display: 'flex', alignItems: 'center' }}>
          <RoleIcon role={role} />
        </span>
        <span
          id={headingId}
          style={{
            flex: 1,
            fontSize: '13px',
            fontWeight: 600,
            color: 'var(--text)',
            textTransform: 'uppercase',
            letterSpacing: '.04em',
          }}
        >
          {roleLabel}
        </span>

        {/* Botón eliminar (solo refuerzo) */}
        {isReinforcement && onRemove && (
          <button
            type="button"
            onClick={onRemove}
            aria-label={t('calc.removeReinforcement')}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: '28px', height: '28px',
              border: 'none', background: 'transparent',
              cursor: 'pointer', color: 'var(--danger)',
              borderRadius: 'var(--radius-sm)',
              transition: 'background var(--dur-fast) var(--ease)',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(201,53,44,.12)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
          >
            <IconTrash />
          </button>
        )}

        {/* Botón colapsar */}
        <button
          type="button"
          aria-expanded={!collapsed}
          aria-controls={bodyId}
          onClick={() => setCollapsed(c => !c)}
          aria-label={collapsed ? t('calc.collapsed') : t('calc.expanded')}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: '28px', height: '28px',
            border: 'none', background: 'transparent',
            cursor: 'pointer', color: 'var(--text-secondary)',
            borderRadius: 'var(--radius-sm)',
            transition: 'background var(--dur-fast) var(--ease)',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-2)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
        >
          <IconChevronDown rotated={!collapsed} />
        </button>
      </div>

      {/* ── Body (colapsable) ── */}
      {!collapsed && (
        <div id={bodyId} style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>

          {/* ── Fila de controles (atacante) ── */}
          {isAttacker && (
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
              <AttackTypeToggle value={attackType} onChange={onAttackTypeChange} />
              <AllianceBonusSelect
                value={allianceBonusAtk}
                onChange={onAllianceBonusAtk}
                ariaLabel={t('calc.allianceBonus')}
              />
              <ArtifactSelect value={artifactType} onChange={onArtifactChange} />

              {/* Héroe colapsable */}
              <button
                type="button"
                aria-expanded={heroExpanded}
                aria-controls={heroId}
                onClick={() => setHeroExpanded(h => !h)}
                style={{
                  height: '26px', padding: '0 8px',
                  border: '1px solid var(--border-strong)',
                  background: heroExpanded ? 'var(--accent-subtle)' : 'var(--surface-2)',
                  color: heroExpanded ? 'var(--accent-text)' : 'var(--text-secondary)',
                  borderColor: heroExpanded ? 'var(--accent)' : 'var(--border-strong)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12px', cursor: 'pointer', fontFamily: 'inherit',
                  display: 'flex', alignItems: 'center', gap: '4px',
                  transition: 'background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease)',
                }}
              >
                {t('calc.hero.expand')}
                <IconChevronDown size={12} rotated={heroExpanded} />
              </button>
            </div>
          )}

          {/* ── Fila de controles (defensor) ── */}
          {isDefender && (
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
              {/* Muro */}
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                <IconShieldFill />
                <NumInput
                  value={wallLevel}
                  onChange={onWallChange}
                  min={0} max={20}
                  ariaLabel={t('calc.wall')}
                  width={42}
                />
              </label>
              {/* Cantero */}
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>⚒</span>
                <NumInput
                  value={stonemasonLevel}
                  onChange={onStonemasonChange}
                  min={0} max={5}
                  ariaLabel={t('calc.stonemason')}
                  width={42}
                />
              </label>
              {/* Bonus alianza */}
              <AllianceBonusSelect
                value={allianceBonusDef}
                onChange={onAllianceBonusDef}
                ariaLabel={t('calc.allianceBonus')}
              />

              {/* Héroe colapsable */}
              <button
                type="button"
                aria-expanded={heroExpanded}
                aria-controls={heroId}
                onClick={() => setHeroExpanded(h => !h)}
                style={{
                  height: '26px', padding: '0 8px',
                  border: '1px solid var(--border-strong)',
                  background: heroExpanded ? 'var(--accent-subtle)' : 'var(--surface-2)',
                  color: heroExpanded ? 'var(--accent-text)' : 'var(--text-secondary)',
                  borderColor: heroExpanded ? 'var(--accent)' : 'var(--border-strong)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12px', cursor: 'pointer', fontFamily: 'inherit',
                  display: 'flex', alignItems: 'center', gap: '4px',
                  transition: 'background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease)',
                }}
              >
                {t('calc.hero.expand')}
                <IconChevronDown size={12} rotated={heroExpanded} />
              </button>
            </div>
          )}

          {/* ── Hero inputs (colapsable, atacante y defensor) ── */}
          {(isAttacker || isDefender) && heroExpanded && (
            <div id={heroId} style={{
              display: 'flex', flexWrap: 'wrap', gap: '8px',
              padding: '10px 12px',
              background: 'var(--surface-2)',
              borderRadius: 'var(--radius-sm)',
            }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '3px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                {isAttacker ? t('calc.hero.attack') : t('calc.hero.defense')}
                <NumInput
                  value={heroPoints}
                  onChange={onHeroPoints}
                  min={0} max={9999}
                  ariaLabel={isAttacker ? t('calc.hero.attack') : t('calc.hero.defense')}
                  width={70}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '3px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                {isAttacker ? t('calc.hero.attackBonus') : t('calc.hero.defenseBonus')}
                <NumInput
                  value={heroBonusPct}
                  onChange={onHeroBonusPct}
                  min={0} max={500}
                  ariaLabel={isAttacker ? t('calc.hero.attackBonus') : t('calc.hero.defenseBonus')}
                  width={60}
                />
              </label>
            </div>
          )}

          {/* ── Selector de tribu ── */}
          <TribeBar
            tribes={availableTribes}
            selectedTribe={tribe}
            onSelect={onTribeChange}
            label={t('calc.tribe.select')}
          />

          {/* ── Cuadrícula de tropas ── */}
          <TroopGrid
            troops={troops}
            values={troopValues}
            onChange={onTroopChange}
            showSmithy={true}
          />
        </div>
      )}
    </section>
  )
}
