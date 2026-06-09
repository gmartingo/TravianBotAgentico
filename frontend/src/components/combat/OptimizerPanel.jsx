/**
 * OptimizerPanel — Formulario del optimizador de combate contra oasis.
 *
 * Tres herramientas (pestañas):
 *   multi_troop  — el usuario elige qué tipos de tropa puede enviar (checkboxes)
 *                  + nivel de herrería por tipo
 *   army_sim     — el usuario introduce las cantidades disponibles de cada tropa
 *   multi_raid   — igual que army_sim pero optimiza para N raids en serie
 *
 * Sección DEFENSA: siempre tribu NATURE, 10 tipos de animal.
 * Sección CONFIGURACIÓN: colapsable. top_n + % ganancia neta mínima + tooltip ⓘ.
 *
 * Props:
 *   atkTribe           — string (tribu seleccionada del atacante)
 *   onAtkTribeChange   — (tribe) => void
 *   troops             — [{ ordinal, name, iconUrl? }] de la tribu del atacante
 *   natureTroops       — [{ ordinal, name, iconUrl? }] de NATURE (para la defensa)
 *   onOptimize         — (body) => void — lanza la petición al padre
 *   optimizing         — boolean
 *   onInputModeChange  — (mode) => void — callback opcional para notificar al padre del cambio de modo
 */
import { useState } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { TribeBar } from './TribeBar.jsx'
import { Spinner, showToast } from '../ui/uiUtils.jsx'

// ── Iconos ─────────────────────────────────────────────────────────────────────

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

// ⓘ tooltip inline — icono + popover con la descripción completa
function InfoTooltip({ text }) {
  const [visible, setVisible] = useState(false)
  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
      <button
        type="button"
        aria-label={text}
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onFocus={() => setVisible(true)}
        onBlur={() => setVisible(false)}
        style={{
          background: 'none',
          border: 'none',
          padding: '0 0 0 4px',
          cursor: 'pointer',
          color: 'var(--text-secondary)',
          fontSize: '13px',
          lineHeight: 1,
          outline: 'none',
        }}
        onKeyDown={e => { if (e.key === 'Escape') setVisible(false) }}
      >
        ⓘ
      </button>
      {visible && (
        <span role="tooltip" style={{
          position: 'absolute',
          insetInlineStart: '100%',
          top: '50%',
          transform: 'translateY(-50%)',
          marginInlineStart: '8px',
          zIndex: 50,
          width: '260px',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          boxShadow: 'var(--shadow-md)',
          padding: '8px 10px',
          fontSize: '11px',
          lineHeight: 1.5,
          color: 'var(--text-secondary)',
          pointerEvents: 'none',
        }}>
          {text}
        </span>
      )}
    </span>
  )
}

// ── Constantes ─────────────────────────────────────────────────────────────────

// IDs de herramienta: alineados con el discriminador `tool` del contrato HTTP
const MODES = [
  { id: 'multi_troop', labelKey: 'calc.optimizer.modeMultiTroop' },
  { id: 'army_sim',    labelKey: 'calc.optimizer.modeArmySim' },
  { id: 'multi_raid',  labelKey: 'calc.optimizer.modeMultiRaid' },
]

// Defaults semánticos de ganancia neta por herramienta (spec §8, nota al pie)
const DEFAULT_MIN_NET_GAIN_PCT = {
  multi_troop: 20,
  army_sim:    50,
  multi_raid:  30,
}

const ATTACKER_TRIBES = [
  { id: 'romans',    labelKey: 'calc.tribe.romans' },
  { id: 'teutons',   labelKey: 'calc.tribe.teutons' },
  { id: 'gauls',     labelKey: 'calc.tribe.gauls' },
  { id: 'egyptians', labelKey: 'calc.tribe.egyptians' },
  { id: 'huns',      labelKey: 'calc.tribe.huns' },
  { id: 'spartans',  labelKey: 'calc.tribe.spartans' },
  { id: 'vikings',   labelKey: 'calc.tribe.vikings' },
]

// ── Componentes internos ───────────────────────────────────────────────────────

// Input numérico compacto reutilizable (sin permitir decimales)
function NumInput({ value, onChange, min = 0, max = 9999, placeholder = '0', ariaLabel, width = 52 }) {
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
        height: '28px',
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

// Input de porcentaje (0–100) con símbolo % a la derecha
function PctInput({ value, onChange, ariaLabel, width = 60 }) {
  return (
    <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
      <input
        type="text"
        inputMode="numeric"
        pattern="[0-9]*"
        value={value === 0 ? '' : value}
        placeholder="0"
        aria-label={ariaLabel}
        onChange={e => {
          const raw = e.target.value.replace(/\D/g, '')
          const n = raw === '' ? 0 : Math.min(100, Math.max(0, Number(raw)))
          onChange(n)
        }}
        onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
        onBlur={e => { e.currentTarget.style.borderColor = 'var(--border-strong)' }}
        style={{
          width: `${width}px`,
          height: '28px',
          padding: '0 20px 0 6px',   /* espacio para el % */
          background: 'var(--surface-2)',
          border: '1px solid var(--border-strong)',
          borderRadius: 'var(--radius-sm)',
          fontSize: '13px',
          fontFamily: 'var(--font-mono)',
          fontVariantNumeric: 'tabular-nums',
          color: 'var(--text)',
          textAlign: 'end',
          outline: 'none',
          transition: 'border-color var(--dur-fast) var(--ease)',
          boxSizing: 'border-box',
        }}
      />
      <span style={{
        position: 'absolute',
        insetInlineEnd: '6px',
        fontSize: '12px',
        color: 'var(--text-tertiary)',
        pointerEvents: 'none',
        userSelect: 'none',
      }}>%</span>
    </div>
  )
}

// Celda de tropa para Multi-Tropa (checkbox + icono + smithy si marcado)
function TroopCheckCell({ troop, checked, smithy, onToggle, onSmithy }) {
  const { t } = useI18n()
  return (
    <div
      role="checkbox"
      aria-checked={checked}
      tabIndex={0}
      onClick={() => onToggle(troop.ordinal)}
      onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); onToggle(troop.ordinal) } }}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '3px',
        padding: '6px 4px',
        borderRadius: 'var(--radius-sm)',
        border: `1px solid ${checked ? 'var(--accent)' : 'var(--border)'}`,
        background: checked ? 'var(--accent-subtle)' : 'var(--surface-2)',
        cursor: 'pointer',
        minWidth: '52px',
        transition: 'border-color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease)',
        opacity: checked ? 1 : 0.5,
        userSelect: 'none',
      }}
      onFocus={e => { e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '2px' }}
      onBlur={e => { e.currentTarget.style.outline = 'none' }}
    >
      {/* Icono */}
      <div style={{ width: '24px', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {troop.iconUrl ? (
          <img src={troop.iconUrl} alt="" style={{ width: '24px', height: '24px', objectFit: 'contain', imageRendering: 'pixelated' }} />
        ) : (
          <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>
            T{troop.ordinal}
          </span>
        )}
      </div>
      {/* Nombre corto */}
      <span style={{ fontSize: '10px', color: checked ? 'var(--accent-text)' : 'var(--text-tertiary)', lineHeight: 1, textAlign: 'center', maxWidth: '48px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {troop.name ?? `T${troop.ordinal}`}
      </span>
      {/* Smithy solo si marcado */}
      {checked && (
        <input
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={2}
          value={smithy === 0 ? '' : smithy}
          placeholder="0"
          aria-label={`${troop.name ?? `T${troop.ordinal}`} — ${t('calc.troop.smithy')}`}
          onClick={e => e.stopPropagation()}
          onChange={e => {
            const raw = e.target.value.replace(/\D/g, '')
            const val = Math.min(20, Math.max(0, Number(raw || 0)))
            onSmithy(troop.ordinal, val)
          }}
          onFocus={e => { e.stopPropagation(); e.currentTarget.style.borderColor = 'var(--accent)' }}
          onBlur={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
          style={{
            width: '38px',
            height: '22px',
            padding: '0 3px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            fontVariantNumeric: 'tabular-nums',
            color: 'var(--text)',
            textAlign: 'center',
            outline: 'none',
            transition: 'border-color var(--dur-fast) var(--ease)',
            boxSizing: 'border-box',
          }}
        />
      )}
    </div>
  )
}

// Celda de tropa para Simulador / Multi-Raid (cantidad disponible + smithy)
function TroopAvailCell({ troop, qty, smithy, onChange }) {
  const { t } = useI18n()
  const isActive = Number(qty) > 0
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '4px',
      opacity: isActive ? 1 : 0.45,
      transition: 'opacity var(--dur-fast) var(--ease)',
      minWidth: '52px',
    }}>
      {/* Icono */}
      <div style={{ width: '52px', height: '28px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {troop.iconUrl ? (
          <img src={troop.iconUrl} alt="" style={{ width: '24px', height: '24px', objectFit: 'contain', imageRendering: 'pixelated' }} />
        ) : (
          <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>T{troop.ordinal}</span>
        )}
      </div>
      {/* Input cantidad disponible */}
      <input
        type="text"
        inputMode="numeric"
        pattern="[0-9]*"
        maxLength={6}
        value={qty === 0 ? '' : qty}
        placeholder="0"
        aria-label={`${troop.name ?? `T${troop.ordinal}`} — ${t('calc.troop.qty')}`}
        onChange={e => {
          const raw = e.target.value.replace(/\D/g, '').slice(0, 6)
          onChange(troop.ordinal, 'qty', raw === '' ? 0 : Number(raw))
        }}
        onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
        onBlur={e => { e.currentTarget.style.borderColor = 'var(--border-strong)' }}
        style={{
          width: '52px', height: '28px', padding: '0 4px',
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
      {/* Smithy */}
      <input
        type="text"
        inputMode="numeric"
        pattern="[0-9]*"
        maxLength={2}
        value={smithy === 0 ? '' : smithy}
        placeholder=""
        aria-label={`${troop.name ?? `T${troop.ordinal}`} — ${t('calc.troop.smithy')}`}
        onChange={e => {
          const raw = e.target.value.replace(/\D/g, '')
          onChange(troop.ordinal, 'smithy', Math.min(20, Math.max(0, Number(raw || 0))))
        }}
        onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
        onBlur={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
        style={{
          width: '52px', height: '24px', padding: '0 4px',
          background: 'transparent',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          fontSize: '12px',
          fontFamily: 'var(--font-mono)',
          fontVariantNumeric: 'tabular-nums',
          color: 'var(--text)',
          textAlign: 'center',
          outline: 'none',
          transition: 'border-color var(--dur-fast) var(--ease)',
          boxSizing: 'border-box',
        }}
      />
    </div>
  )
}

// Celda de animal (defensa NATURE)
function AnimalCell({ troop, qty, onChange }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '4px',
      opacity: Number(qty) > 0 ? 1 : 0.45,
      transition: 'opacity var(--dur-fast) var(--ease)',
      minWidth: '52px',
    }}>
      <div style={{ width: '52px', height: '28px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {troop.iconUrl ? (
          <img src={troop.iconUrl} alt="" style={{ width: '24px', height: '24px', objectFit: 'contain', imageRendering: 'pixelated' }} />
        ) : (
          <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>T{troop.ordinal}</span>
        )}
      </div>
      <input
        type="text"
        inputMode="numeric"
        pattern="[0-9]*"
        maxLength={5}
        value={qty === 0 ? '' : qty}
        placeholder="0"
        aria-label={troop.name ?? `T${troop.ordinal}`}
        onChange={e => {
          const raw = e.target.value.replace(/\D/g, '').slice(0, 5)
          onChange(troop.ordinal, raw === '' ? 0 : Number(raw))
        }}
        onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
        onBlur={e => { e.currentTarget.style.borderColor = 'var(--border-strong)' }}
        style={{
          width: '52px', height: '28px', padding: '0 4px',
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
    </div>
  )
}

// ── Cabecera de sección ────────────────────────────────────────────────────────
function SectionHeader({ icon, titleKey, children }) {
  const { t } = useI18n()
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      padding: '10px 14px',
      borderBottom: '1px solid var(--border)',
      background: 'var(--surface-2)',
    }}>
      <span style={{ fontSize: '14px' }} aria-hidden="true">{icon}</span>
      <span style={{
        flex: 1,
        fontSize: '13px',
        fontWeight: 600,
        color: 'var(--text)',
        textTransform: 'uppercase',
        letterSpacing: '.04em',
      }}>
        {t(titleKey)}
      </span>
      {children}
    </div>
  )
}

// ── OptimizerPanel ─────────────────────────────────────────────────────────────

export function OptimizerPanel({
  atkTribe,
  onAtkTribeChange,
  troops,               // tropas del atacante (tribu seleccionada)
  natureTroops,         // tropas de NATURE para la defensa
  onOptimize,
  optimizing,
  onInputModeChange,    // callback opcional: (mode) => void
  onMinNetGainPctChange, // callback opcional: (pct) => void
}) {
  const { t } = useI18n()

  // ── Herramienta activa ─────────────────────────────────────────────────────
  const [inputMode, setInputMode] = useState('multi_troop') // 'multi_troop' | 'army_sim' | 'multi_raid'

  // ── Multi-Tropa: set de ordinales marcados + smithy por tipo ───────────────
  const [checkedOrdinals, setCheckedOrdinals] = useState(new Set())
  const [smithyA, setSmithyA] = useState({}) // { ordinal: level }

  function toggleOrdinal(ordinal) {
    setCheckedOrdinals(prev => {
      const next = new Set(prev)
      if (next.has(ordinal)) next.delete(ordinal)
      else next.add(ordinal)
      return next
    })
  }

  function setSmithyALevel(ordinal, level) {
    setSmithyA(prev => ({ ...prev, [ordinal]: level }))
  }

  // ── Simulador / Multi-Raid: cantidades disponibles + smithy ───────────────
  const [troopValues, setTroopValues] = useState({}) // { ordinal: { qty, smithy } }

  function handleTroopChange(ordinal, field, value) {
    setTroopValues(prev => ({
      ...prev,
      [ordinal]: { ...(prev[ordinal] ?? { qty: 0, smithy: 0 }), [field]: value },
    }))
  }

  // ── Defensa: cantidades de animales ───────────────────────────────────────
  const [animalQty, setAnimalQty] = useState({}) // { ordinal: qty }

  function handleAnimalChange(ordinal, qty) {
    setAnimalQty(prev => ({ ...prev, [ordinal]: qty }))
  }

  // ── Configuración ──────────────────────────────────────────────────────────
  // Sección de configuración colapsada por defecto — es ajuste fino.
  const [configExpanded, setConfigExpanded] = useState(false)
  const [topN, setTopN] = useState(3)

  // % ganancia neta mínima — default semántico por herramienta (spec §8)
  // Se reinicia al default del nuevo modo al cambiar de pestaña.
  const [minNetGainPct, setMinNetGainPct] = useState(DEFAULT_MIN_NET_GAIN_PCT['multi_troop'])

  // Multi-Raid: mínimo de oasis (n_min_raids). null = el optimizador decide.
  const [nMinRaids, setNMinRaids] = useState(null)

  // Handler de cambio de herramienta: aplica el default de % al entrar a cada pestaña.
  function handleModeChange(mode) {
    setInputMode(mode)
    const defaultPct = DEFAULT_MIN_NET_GAIN_PCT[mode]
    setMinNetGainPct(defaultPct)
    onInputModeChange?.(mode)
    onMinNetGainPctChange?.(defaultPct)
  }

  // Handler de cambio del % ganancia neta: notifica al padre si hay callback.
  function handleMinNetGainPctChange(pct) {
    setMinNetGainPct(pct)
    onMinNetGainPctChange?.(pct)
  }

  // ── Construir body ─────────────────────────────────────────────────────────
  function buildBody() {
    const oasisTroops = natureTroops
      .filter(tr => Number(animalQty[tr.ordinal] ?? 0) > 0)
      .map(tr => ({ ordinal: tr.ordinal, quantity: Number(animalQty[tr.ordinal]) }))

    // scoring_mode se infiere desde tool en el handler del backend,
    // pero lo enviamos igualmente para retrocompatibilidad explícita.
    const scoring_mode = inputMode === 'multi_raid' ? 'aggregate' : 'single'

    const baseConfig = {
      tool: inputMode,
      server_speed: 1.0,
      top_n: topN,
      min_net_gain_pct: minNetGainPct,
      scoring_mode,
      // n_min_raids solo se envía en Multi-Raid y si el usuario lo ha rellenado
      ...(inputMode === 'multi_raid' && nMinRaids != null ? { n_min_raids: nMinRaids } : {}),
    }

    if (inputMode === 'multi_troop') {
      const troop_types = troops
        .filter(tr => checkedOrdinals.has(tr.ordinal))
        .map(tr => ({
          ordinal: tr.ordinal,
          smithy_level: Number(smithyA[tr.ordinal] ?? 0),
        }))

      return {
        attacker: {
          tribe: atkTribe,
          troop_types,
          hero_attack_points: 0,
          hero_attack_bonus_percent: 0,
          alliance_bonus: 0,
        },
        oasis_defense: { troops: oasisTroops },
        config: baseConfig,
      }
    } else {
      // army_sim y multi_raid usan village_troops (mismo formulario)
      const village_troops = troops
        .filter(tr => Number(troopValues[tr.ordinal]?.qty ?? 0) > 0)
        .map(tr => ({
          ordinal: tr.ordinal,
          quantity_available: Number(troopValues[tr.ordinal]?.qty ?? 0),
          smithy_level: Number(troopValues[tr.ordinal]?.smithy ?? 0),
        }))

      return {
        attacker: {
          tribe: atkTribe,
          village_troops,
          hero_attack_points: 0,
          hero_attack_bonus_percent: 0,
          alliance_bonus: 0,
        },
        oasis_defense: { troops: oasisTroops },
        config: baseConfig,
      }
    }
  }

  function handleOptimize() {
    // Validar defensa del oasis: al menos un animal con cantidad > 0
    const hasOasis = natureTroops.some(tr => Number(animalQty[tr.ordinal] ?? 0) > 0)
    if (!hasOasis) {
      showToast(t('calc.optimizer.errorNoOasis'))
      return
    }

    // Validar tropas atacantes según la herramienta
    if (inputMode === 'multi_troop') {
      if (checkedOrdinals.size === 0) {
        showToast(t('calc.optimizer.errorNoTroopTypes'))
        return
      }
    } else {
      // army_sim y multi_raid
      const hasVillage = troops.some(tr => Number(troopValues[tr.ordinal]?.qty ?? 0) > 0)
      if (!hasVillage) {
        showToast(t('calc.optimizer.errorNoVillageTroops'))
        return
      }
    }

    onOptimize(buildBody())
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const configBodyId = 'opt-config-body'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>

      {/* ── Sección atacante ── */}
      <section
        role="region"
        aria-label={t('calc.attacker')}
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          overflow: 'hidden',
          marginBottom: '8px',
        }}
      >
        <SectionHeader icon="⚔" titleKey="calc.attacker">
          {/* Toggle de herramienta: Multi-Tropa / Simulador / Multi-Raid */}
          <div
            role="radiogroup"
            aria-label={t('calc.optimizer.inputMode')}
            style={{
              display: 'flex',
              borderRadius: 'var(--radius-sm)',
              overflow: 'hidden',
              border: '1px solid var(--border-strong)',
            }}
          >
            {MODES.map(({ id, labelKey }) => {
              const isActive = inputMode === id
              return (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={isActive}
                  onClick={() => handleModeChange(id)}
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
                    whiteSpace: 'nowrap',
                    transition: 'background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease)',
                  }}
                >
                  {t(labelKey)}
                </button>
              )
            })}
          </div>
        </SectionHeader>

        <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {/* Selector de tribu del atacante */}
          <TribeBar
            tribes={ATTACKER_TRIBES}
            selectedTribe={atkTribe}
            onSelect={onAtkTribeChange}
            label={t('calc.tribe.select')}
          />

          {/* Hint de Multi-Raid */}
          {inputMode === 'multi_raid' && (
            <div style={{
              fontSize: '12px',
              color: 'var(--accent-text)',
              fontStyle: 'italic',
              padding: '4px 8px',
              background: 'var(--accent-subtle)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--accent)',
            }}>
              {t('calc.optimizer.modeCHint')}
            </div>
          )}

          {/* Multi-Tropa — checkboxes de tipos de tropa */}
          {inputMode === 'multi_troop' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>
                {t('calc.optimizer.modeAHint')}
              </div>
              <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', minWidth: 'max-content' }}>
                  {troops.map(troop => (
                    <TroopCheckCell
                      key={troop.ordinal}
                      troop={troop}
                      checked={checkedOrdinals.has(troop.ordinal)}
                      smithy={smithyA[troop.ordinal] ?? 0}
                      onToggle={toggleOrdinal}
                      onSmithy={setSmithyALevel}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Simulador / Multi-Raid — cantidades disponibles (mismo formulario) */}
          {(inputMode === 'army_sim' || inputMode === 'multi_raid') && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>
                {t('calc.optimizer.modeBHint')}
              </div>
              <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                <div style={{ display: 'flex', gap: '6px', minWidth: 'max-content' }}>
                  {troops.map(troop => {
                    const val = troopValues[troop.ordinal] ?? { qty: 0, smithy: 0 }
                    return (
                      <TroopAvailCell
                        key={troop.ordinal}
                        troop={troop}
                        qty={val.qty}
                        smithy={val.smithy}
                        onChange={handleTroopChange}
                      />
                    )
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Multi-Raid — campo opcional "Mínimo de oasis" (n_min_raids) */}
          {inputMode === 'multi_raid' && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 10px',
              background: 'var(--surface-2)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)',
            }}>
              <label
                htmlFor="opt-n-min-raids"
                style={{ fontSize: '12px', color: 'var(--text-secondary)', flex: 1 }}
              >
                {t('calc.optimizer.nMinRaids.label')}
              </label>
              <input
                id="opt-n-min-raids"
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={4}
                value={nMinRaids == null ? '' : nMinRaids}
                placeholder={t('calc.optimizer.nMinRaids.placeholder')}
                aria-label={t('calc.optimizer.nMinRaids.label')}
                onChange={e => {
                  const raw = e.target.value.replace(/\D/g, '')
                  setNMinRaids(raw === '' ? null : Math.max(1, Number(raw)))
                }}
                onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
                onBlur={e => { e.currentTarget.style.borderColor = 'var(--border-strong)' }}
                style={{
                  width: '64px', height: '26px', padding: '0 6px',
                  background: 'var(--surface)',
                  border: '1px solid var(--border-strong)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12px', fontFamily: 'var(--font-mono)',
                  fontVariantNumeric: 'tabular-nums',
                  color: 'var(--text)', textAlign: 'center',
                  outline: 'none', boxSizing: 'border-box',
                  transition: 'border-color var(--dur-fast) var(--ease)',
                }}
              />
            </div>
          )}
        </div>
      </section>

      {/* ── Sección defensa oasis ── */}
      <section
        role="region"
        aria-label={t('calc.optimizer.oasisDefense')}
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          overflow: 'hidden',
          marginBottom: '8px',
        }}
      >
        <SectionHeader icon="🐾" titleKey="calc.optimizer.oasisDefense" />
        <div style={{ padding: '12px 14px' }}>
          {natureTroops.length === 0 ? (
            <div style={{ fontSize: '13px', color: 'var(--text-tertiary)', padding: '4px 0' }}>—</div>
          ) : (
            <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
              <div style={{ display: 'flex', gap: '6px', minWidth: 'max-content' }}>
                {natureTroops.map(troop => (
                  <AnimalCell
                    key={troop.ordinal}
                    troop={troop}
                    qty={animalQty[troop.ordinal] ?? 0}
                    onChange={handleAnimalChange}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ── Sección configuración (colapsable) ── */}
      <section
        role="region"
        aria-label={t('calc.optimizer.config')}
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          overflow: 'hidden',
          marginBottom: '16px',
        }}
      >
        {/* Header colapsable */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '10px 14px',
          borderBottom: configExpanded ? '1px solid var(--border)' : 'none',
          background: 'var(--surface-2)',
          cursor: 'pointer',
          userSelect: 'none',
        }}
          onClick={() => setConfigExpanded(c => !c)}
          role="button"
          aria-expanded={configExpanded}
          aria-controls={configBodyId}
          tabIndex={0}
          onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); setConfigExpanded(c => !c) } }}
          onFocus={e => { e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '-2px' }}
          onBlur={e => { e.currentTarget.style.outline = 'none' }}
        >
          <span style={{ fontSize: '14px' }} aria-hidden="true">⚙</span>
          <span style={{
            flex: 1,
            fontSize: '13px',
            fontWeight: 600,
            color: 'var(--text)',
            textTransform: 'uppercase',
            letterSpacing: '.04em',
          }}>
            {t('calc.optimizer.config')}
          </span>
          <IconChevronDown rotated={configExpanded} />
        </div>

        {configExpanded && (
          <div id={configBodyId} style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* Top N */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ flex: 1, fontSize: '12px', color: 'var(--text-secondary)', minWidth: '140px' }}>
                {t('calc.optimizer.topN')}
              </span>
              <NumInput
                value={topN}
                onChange={setTopN}
                min={1}
                max={20}
                ariaLabel={t('calc.optimizer.topN')}
                width={60}
              />
            </div>

            {/* Separador */}
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: '10px' }}>
              {/* % Ganancia neta mínima — control único que reemplaza los 5 pesos */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <label
                  htmlFor="opt-min-net-gain"
                  style={{ flex: 1, fontSize: '12px', color: 'var(--text-secondary)', minWidth: '140px' }}
                >
                  {t('calc.optimizer.minNetGainPct.label')}
                </label>
                <PctInput
                  value={minNetGainPct}
                  onChange={handleMinNetGainPctChange}
                  ariaLabel={t('calc.optimizer.minNetGainPct.label')}
                  width={68}
                />
                {/* id para el label + accesibilidad del input */}
                <InfoTooltip text={t('calc.optimizer.minNetGainPct.tooltip')} />
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ── Botón OPTIMIZAR ── */}
      <button
        type="button"
        onClick={handleOptimize}
        disabled={optimizing}
        aria-busy={optimizing}
        style={{
          height: '40px',
          width: '100%',
          background: optimizing ? 'var(--btn-primary-hover)' : 'var(--btn-primary-bg)',
          color: 'var(--btn-primary-text)',
          border: 'none',
          borderRadius: 'var(--radius-sm)',
          fontSize: '15px',
          fontWeight: 600,
          cursor: optimizing ? 'wait' : 'pointer',
          fontFamily: 'inherit',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '8px',
          transition: 'background var(--dur-fast) var(--ease)',
          letterSpacing: '-0.01em',
          outline: 'none',
        }}
        onMouseEnter={e => { if (!optimizing) e.currentTarget.style.background = 'var(--btn-primary-hover)' }}
        onMouseLeave={e => { if (!optimizing) e.currentTarget.style.background = 'var(--btn-primary-bg)' }}
        onFocus={e => { e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '2px' }}
        onBlur={e => { e.currentTarget.style.outline = 'none' }}
      >
        {optimizing ? (
          <>
            <Spinner size={16} />
            {t('calc.optimizer.optimizing')}
          </>
        ) : (
          t('calc.optimizer.optimize')
        )}
      </button>
    </div>
  )
}
