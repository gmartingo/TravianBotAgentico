/**
 * OptimizerPanel — Formulario del optimizador de combate contra oasis.
 *
 * Dos modos de entrada:
 *   Modo A — el usuario elige qué tipos de tropa puede enviar (checkboxes)
 *             + nivel de herrería por tipo
 *   Modo B — el usuario introduce las cantidades disponibles de cada tropa
 *             (mismo grid de TroopGrid pero con máximos, no objetivo)
 *
 * Sección DEFENSA: siempre tribu NATURE, 10 tipos de animal.
 * Sección CONFIGURACIÓN: colapsable. top_n + sliders de pesos.
 *
 * Props:
 *   atkTribe           — string (tribu seleccionada del atacante)
 *   troops             — [{ ordinal, name, iconUrl? }] de la tribu del atacante
 *   natureTroops       — [{ ordinal, name, iconUrl? }] de NATURE (para la defensa)
 *   onOptimize         — (body) => void — lanza la petición al padre
 *   optimizing         — boolean
 *
 * No gestiona estado externo, es autocontenido.
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

// ── Constantes ─────────────────────────────────────────────────────────────────

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

// Input numérico compacto reutilizable
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

// Celda de tropa para el Modo A (checkbox + icono + smithy si marcado)
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

// Celda de tropa para el Modo B (cantidad disponible + smithy)
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

// Slider de peso con valor visible
// Etiqueta semántica del valor actual del peso.
// 0 = ignorar este criterio, ~1 = importancia normal, 2 = doble prioridad.
function weightLabel(value, t) {
  if (value <= 0.05) return t('calc.optimizer.weight.value.ignore')
  if (value < 0.85)  return t('calc.optimizer.weight.value.low')
  if (value <= 1.15) return t('calc.optimizer.weight.value.normal')
  if (value < 1.85)  return t('calc.optimizer.weight.value.high')
  return t('calc.optimizer.weight.value.max')
}

// Slider de peso con doble nivel de ayuda:
//  - Cabecera: label + slider + valor numérico + "etiqueta semántica" del valor
//  - Pie:      "← ignorar"  ·  hint específico ("Más alto = X")  ·  "doble →"
// hintKey es la frase concreta para ESTE criterio (qué significa subirlo).
function WeightSlider({ labelKey, hintKey, value, onChange }) {
  const { t } = useI18n()
  // Pista para lectores de pantalla: el aria-valuetext describe el peso de
  // forma comprensible ("normal", "ignorar", etc.) en vez de solo el número.
  const semantic = weightLabel(value, t)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
      {/* Fila principal: label + slider + valor + etiqueta semántica */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span style={{ flex: 1, fontSize: '12px', color: 'var(--text-secondary)', minWidth: '160px' }}>
          {t(labelKey)}
        </span>
        <input
          type="range"
          min={0}
          max={2}
          step={0.1}
          value={value}
          onChange={e => onChange(Number(e.target.value))}
          aria-label={t(labelKey)}
          aria-valuetext={`${value.toFixed(1)} — ${semantic}`}
          list={`ticks-${labelKey}`}
          style={{ flex: 2, accentColor: 'var(--accent)', cursor: 'pointer' }}
        />
        {/* Marcas nativas a 0 / 1 / 2 — el navegador las pinta debajo del slider */}
        <datalist id={`ticks-${labelKey}`}>
          <option value="0" />
          <option value="1" />
          <option value="2" />
        </datalist>
        <span style={{
          minWidth: '64px',
          textAlign: 'end',
          fontSize: '11px',
          color: 'var(--text)',
          display: 'inline-flex',
          alignItems: 'baseline',
          justifyContent: 'flex-end',
          gap: '4px',
        }}>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontVariantNumeric: 'tabular-nums',
            fontSize: '12px',
            fontWeight: 600,
          }}>
            {value.toFixed(1)}
          </span>
          <span style={{ color: 'var(--text-tertiary)', fontSize: '10px', whiteSpace: 'nowrap' }}>
            {semantic}
          </span>
        </span>
      </div>

      {/* Pie de ayuda: extremos + frase específica del criterio.
          Span completo del ancho para evitar problemas de alineación con la
          columna del slider en distintos tamaños de panel. */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        paddingInlineStart: '4px',
      }}>
        <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
          ← {t('calc.optimizer.weight.endLeft')}
        </span>
        <span style={{
          flex: 1,
          fontSize: '11px',
          color: 'var(--text-secondary)',
          fontStyle: 'italic',
          textAlign: 'center',
          lineHeight: 1.35,
        }}>
          {t(hintKey)}
        </span>
        <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
          {t('calc.optimizer.weight.endRight')} →
        </span>
      </div>
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
  troops,           // tropas del atacante (tribu seleccionada)
  natureTroops,     // tropas de NATURE para la defensa
  onOptimize,
  optimizing,
}) {
  const { t } = useI18n()

  // ── Modo A/B ───────────────────────────────────────────────────────────────
  const [inputMode, setInputMode] = useState('A') // 'A' | 'B'

  // ── Modo A: set de ordinales marcados + smithy por tipo ────────────────────
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

  // ── Modo B: cantidades disponibles + smithy por tropa ─────────────────────
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
  const [configExpanded, setConfigExpanded] = useState(true)
  const [topN, setTopN] = useState(3)
  const [wResources, setWResources] = useState(1.0)
  const [wLosses, setWLosses] = useState(1.0)
  const [wTroops, setWTroops] = useState(0.5)
  const [wTravel, setWTravel] = useState(0.0)

  // ── Construir body ─────────────────────────────────────────────────────────
  function buildBody() {
    const oasisTroops = natureTroops
      .filter(t => Number(animalQty[t.ordinal] ?? 0) > 0)
      .map(t => ({ ordinal: t.ordinal, quantity: Number(animalQty[t.ordinal]) }))

    const baseConfig = {
      server_speed: 1.0,
      top_n: topN,
      optimization_weights: {
        resources_gained: wResources,
        total_losses: wLosses,
        troops_sent: wTroops,
        travel_time: wTravel,
      },
    }

    if (inputMode === 'A') {
      const troop_types = troops
        .filter(t => checkedOrdinals.has(t.ordinal))
        .map(t => ({
          ordinal: t.ordinal,
          smithy_level: Number(smithyA[t.ordinal] ?? 0),
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
      const village_troops = troops
        .filter(t => Number(troopValues[t.ordinal]?.qty ?? 0) > 0)
        .map(t => ({
          ordinal: t.ordinal,
          quantity_available: Number(troopValues[t.ordinal]?.qty ?? 0),
          smithy_level: Number(troopValues[t.ordinal]?.smithy ?? 0),
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
    const hasOasis = natureTroops.some(t => Number(animalQty[t.ordinal] ?? 0) > 0)
    if (!hasOasis) {
      showToast(t('calc.optimizer.errorNoOasis'))
      return
    }

    // Validar tropas atacantes según el modo
    if (inputMode === 'A') {
      if (checkedOrdinals.size === 0) {
        showToast(t('calc.optimizer.errorNoTroopTypes'))
        return
      }
    } else {
      const hasVillage = troops.some(t => Number(troopValues[t.ordinal]?.qty ?? 0) > 0)
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
          {/* Toggle Modo A / Modo B */}
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
            {['A', 'B'].map(mode => {
              const isActive = inputMode === mode
              return (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={isActive}
                  onClick={() => setInputMode(mode)}
                  style={{
                    height: '26px',
                    padding: '0 12px',
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
                  {t(`calc.optimizer.mode${mode}`)}
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

          {/* Modo A — checkboxes de tipos de tropa */}
          {inputMode === 'A' && (
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

          {/* Modo B — cantidades disponibles */}
          {inputMode === 'B' && (
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
          <div id={configBodyId} style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {/* Top N */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ flex: 1, fontSize: '12px', color: 'var(--text-secondary)', minWidth: '160px' }}>
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
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: '8px' }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: '4px' }}>
                {t('calc.optimizer.weights')}
              </div>
              {/* Explicación de la escala 0..2 para todos los pesos */}
              <div style={{
                fontSize: '11px',
                color: 'var(--text-tertiary)',
                marginBottom: '10px',
                lineHeight: 1.4,
              }}>
                {t('calc.optimizer.weights.intro')}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <WeightSlider
                  labelKey="calc.optimizer.weight.resources"
                  hintKey="calc.optimizer.weight.resources.hint"
                  value={wResources}
                  onChange={setWResources}
                />
                <WeightSlider
                  labelKey="calc.optimizer.weight.losses"
                  hintKey="calc.optimizer.weight.losses.hint"
                  value={wLosses}
                  onChange={setWLosses}
                />
                <WeightSlider
                  labelKey="calc.optimizer.weight.troops"
                  hintKey="calc.optimizer.weight.troops.hint"
                  value={wTroops}
                  onChange={setWTroops}
                />
                <WeightSlider
                  labelKey="calc.optimizer.weight.travel"
                  hintKey="calc.optimizer.weight.travel.hint"
                  value={wTravel}
                  onChange={setWTravel}
                />
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
