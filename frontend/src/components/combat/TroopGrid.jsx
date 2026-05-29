/**
 * TroopGrid — Tres filas de la cuadrícula de tropas.
 *
 * Fila 1: iconos de tropa (img 24px del catálogo de iconos)
 * Fila 2: [🛡 icono] inputs de cantidad (5 dígitos, placeholder "0")
 * Fila 3: [🔨 icono] inputs de smithy (placeholder vacío = nivel 0)
 *
 * Props:
 *   troops       — array de { ordinal, name, iconUrl? } (en orden de la tribu)
 *   values       — { [ordinal]: { qty: number, smithy: number } }
 *   onChange     — (ordinal, field, value) => void   field = 'qty' | 'smithy'
 *   showSmithy   — boolean (true por defecto)
 *   readOnly     — boolean (solo lectura, deshabilita inputs)
 *
 * Accesibilidad:
 *   - Cada input tiene aria-label con nombre de tropa + tipo (cantidad / herrería)
 *   - Iconos con alt vacío (decorativos, el nombre va en el aria-label del input)
 *   - grid con scroll horizontal en móvil (overflow-x: auto en el contenedor)
 *
 * Estilos:
 *   - Tropas con qty=0 → opacity 0.45 en la columna
 *   - Al escribir qty > 0 → opacity 1 (activada)
 *   - font-mono + tabular-nums en todos los inputs numéricos
 *   - inputs compactos: ancho fijo 52px, altura 28px
 */
import { useI18n } from '../../i18n/index.jsx'

// Icono escudo (fila cantidad)
function IconShield() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '14px', height: '14px', flexShrink: 0, color: 'var(--text-tertiary)' }}
      aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

// Icono herrería (fila smithy)
function IconAnvil() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round"
      style={{ width: '14px', height: '14px', flexShrink: 0, color: 'var(--text-tertiary)' }}
      aria-hidden="true">
      <rect x="2" y="14" width="20" height="4" rx="1" />
      <path d="M6 14V9a6 6 0 0 1 12 0v5" />
      <line x1="9" y1="18" x2="9" y2="22" />
      <line x1="15" y1="18" x2="15" y2="22" />
    </svg>
  )
}

const INPUT_W = 52   // px — ancho de cada celda de input
const CELL_GAP = 4   // px — gap entre columnas

const inputBase = {
  width: `${INPUT_W}px`,
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
}

const inputSmall = {
  ...inputBase,
  height: '24px',
  fontSize: '12px',
  background: 'transparent',
  border: '1px solid var(--border)',
}

function TroopCell({ troop, qty, smithy, onChange, showSmithy, readOnly }) {
  const { t } = useI18n()
  const isActive = Number(qty) > 0
  const colOpacity = isActive ? 1 : 0.45

  function handleQtyChange(e) {
    const raw = e.target.value.replace(/\D/g, '').slice(0, 5)
    onChange(troop.ordinal, 'qty', raw === '' ? '' : Number(raw))
  }

  function handleSmithyChange(e) {
    const raw = e.target.value.replace(/\D/g, '')
    const val = Math.min(20, Math.max(0, Number(raw || 0)))
    onChange(troop.ordinal, 'smithy', val)
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: `${CELL_GAP}px`,
      opacity: colOpacity,
      transition: 'opacity var(--dur-fast) var(--ease)',
      flexShrink: 0,
    }}>
      {/* Icono de tropa */}
      <div style={{
        width: `${INPUT_W}px`,
        height: '28px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        {troop.iconUrl ? (
          <img
            src={troop.iconUrl}
            alt=""
            style={{ width: '24px', height: '24px', objectFit: 'contain', imageRendering: 'pixelated' }}
          />
        ) : (
          <span style={{
            fontSize: '10px',
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-tertiary)',
            lineHeight: 1,
          }}>
            T{troop.ordinal}
          </span>
        )}
      </div>

      {/* Input cantidad */}
      <input
        type="text"
        inputMode="numeric"
        pattern="[0-9]*"
        maxLength={5}
        value={qty === '' ? '' : (qty === 0 ? '' : qty)}
        placeholder="0"
        readOnly={readOnly}
        aria-label={`${troop.name ?? `T${troop.ordinal}`} — ${t('calc.troop.qty')}`}
        onChange={handleQtyChange}
        onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
        onBlur={e => { e.currentTarget.style.borderColor = 'var(--border-strong)' }}
        style={{
          ...inputBase,
          cursor: readOnly ? 'default' : 'text',
        }}
      />

      {/* Input herrería */}
      {showSmithy !== false && (
        <input
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={2}
          value={smithy === 0 || smithy === '' ? '' : smithy}
          placeholder=""
          readOnly={readOnly}
          aria-label={`${troop.name ?? `T${troop.ordinal}`} — ${t('calc.troop.smithy')}`}
          onChange={handleSmithyChange}
          onFocus={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
          onBlur={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
          style={{
            ...inputSmall,
            cursor: readOnly ? 'default' : 'text',
          }}
        />
      )}
    </div>
  )
}

export function TroopGrid({ troops, values, onChange, showSmithy = true, readOnly = false }) {
  const { t } = useI18n()

  if (!troops || troops.length === 0) {
    return (
      <div style={{ fontSize: '13px', color: 'var(--text-tertiary)', padding: '8px 0' }}>
        —
      </div>
    )
  }

  return (
    <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '6px',
        minWidth: 'max-content',
      }}>
        {/* Columna de etiquetas (iconos de fila) */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: `${CELL_GAP}px`,
          flexShrink: 0,
          paddingTop: '32px', // alinear con las filas de input (icono 28px + gap 4px)
        }}>
          {/* Espacio para icono de tropa (fila 1) */}
          <div style={{ height: '28px' }} />
          {/* Etiqueta fila cantidad */}
          <div style={{ height: '28px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <IconShield />
          </div>
          {/* Etiqueta fila smithy */}
          {showSmithy !== false && (
            <div style={{ height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <IconAnvil />
            </div>
          )}
        </div>

        {/* Columnas de tropas */}
        {troops.map(troop => {
          const val = values?.[troop.ordinal] ?? { qty: 0, smithy: 0 }
          return (
            <TroopCell
              key={troop.ordinal}
              troop={troop}
              qty={val.qty}
              smithy={val.smithy}
              onChange={onChange}
              showSmithy={showSmithy}
              readOnly={readOnly}
            />
          )
        })}
      </div>
    </div>
  )
}
