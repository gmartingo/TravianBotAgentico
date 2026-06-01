/**
 * BlockEditor — Editor de bloques de un día.
 *
 * Props:
 *  - blocks {Array}      — [{start, end, mode}] — estado local editable
 *  - isDefault {boolean} — mostrar hint "usando configuración por defecto"
 *  - dayLabel {string}   — nombre del día (para el título y el toast)
 *  - saving {boolean}    — botón guardar en cargando
 *  - apiError {string|null} — mensaje de error 422 de la API
 *  - onChange {function} — fn(newBlocks) → el padre actualiza su estado local
 *  - onSave {function}   — fn(blocks) → dispara el PUT
 *
 * Reglas del spec:
 *  - start del primer bloque = 00:00 (fijo, no editable)
 *  - start de los demás = end del bloque anterior (calculado automáticamente)
 *  - end = <input type="time"> + opción 24:00 (valor "24:00" en el state)
 *  - Validación en vivo en onChange: timeline sin huecos ni solapes
 *  - Botón "✕" oculto si solo hay un bloque
 *  - [+] Añadir bloque: inserta al final con start=end_del_último, end=24:00
 *
 * Spec §6 (wireframe editor), §7 (estados), §12 (interacciones).
 */
import { useI18n } from '../../i18n/index.jsx'
import { Spinner } from '../ui/uiUtils.jsx'
import { TimelineBar, TimelineCoverageIndicator, validateCoverage, timeToMin, minToTime } from './TimelineBar.jsx'

// ── BlockRow ──────────────────────────────────────────────────────────────────

function BlockRow({ block, index, totalBlocks, onChange, onRemove }) {
  const { t } = useI18n()

  const isFirstBlock = index === 0
  const isOnlyBlock = totalBlocks === 1

  // Para el input type=time, 24:00 no es válido → mostramos 23:59 como proxy
  // pero internamente guardamos '24:00'
  const endDisplayValue = block.end === '24:00' ? '23:59' : block.end

  function handleEndChange(val) {
    // Si el usuario pone 23:59 Y es el último bloque, interpretar como 24:00
    const isLastBlock = index === totalBlocks - 1
    const normalized = (val === '23:59' && isLastBlock) ? '24:00' : val
    onChange(index, 'end', normalized)
  }

  function handleModeChange(val) {
    onChange(index, 'mode', val)
  }

  const modeCls = block.mode?.toLowerCase() === 'hardcore'
    ? 'var(--mode-hardcore)'
    : block.mode?.toLowerCase() === 'idle'
      ? 'var(--mode-idle)'
      : 'var(--mode-disconnected)'

  return (
    <tr>
      {/* DESDE */}
      <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--border)', verticalAlign: 'middle' }}>
        <input
          type="time"
          value={block.start === '24:00' ? '23:59' : block.start}
          readOnly={true}
          aria-label={t('session.editor.from') + ' ' + (index + 1)}
          tabIndex={isFirstBlock ? 0 : -1}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '13px',
            padding: '4px 6px',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--surface-2)',
            color: 'var(--text-secondary)',
            fontVariantNumeric: 'tabular-nums',
            pointerEvents: 'none',
            // iOS: font-size ≥16px para evitar auto-zoom
            minHeight: '36px',
          }}
        />
      </td>

      {/* HASTA */}
      <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--border)', verticalAlign: 'middle' }}>
        <input
          type="time"
          value={endDisplayValue}
          step="300"
          onChange={e => handleEndChange(e.target.value)}
          aria-label={t('session.editor.to') + ' ' + (index + 1)}
          style={{
            fontFamily: 'var(--font-mono)',
            // iOS: font-size ≥16px para evitar auto-zoom en Safari móvil
            fontSize: 'max(13px, 16px)',
            padding: '4px 6px',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--surface)',
            color: 'var(--text)',
            fontVariantNumeric: 'tabular-nums',
            minHeight: '36px',
          }}
        />
      </td>

      {/* MODO */}
      <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--border)', verticalAlign: 'middle' }}>
        <select
          value={block.mode?.toLowerCase() ?? 'disconnected'}
          onChange={e => handleModeChange(e.target.value)}
          aria-label={t('session.editor.mode') + ' ' + (index + 1)}
          style={{
            fontFamily: 'inherit',
            fontSize: '13px',
            padding: '4px 6px',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--surface)',
            color: modeCls,
            cursor: 'pointer',
            minHeight: '36px',
          }}
        >
          <option value="hardcore">{t('session.mode.hardcore')}</option>
          <option value="idle">{t('session.mode.idle')}</option>
          <option value="disconnected">{t('session.mode.disconnected')}</option>
        </select>
      </td>

      {/* BORRAR */}
      <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--border)', verticalAlign: 'middle', width: '32px' }}>
        {!isOnlyBlock && (
          <button
            type="button"
            onClick={() => onRemove(index)}
            aria-label={t('session.editor.removeBlock') + ' ' + (index + 1)}
            title={t('session.editor.removeBlock')}
            style={{
              width: '28px', height: '28px',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              background: 'transparent',
              color: 'var(--text-tertiary)',
              cursor: 'pointer',
              display: 'grid', placeItems: 'center',
              fontSize: '14px',
              fontFamily: 'inherit',
              transition: 'background var(--dur-fast), color var(--dur-fast)',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = 'var(--danger-subtle)'
              e.currentTarget.style.color = 'var(--danger)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = 'transparent'
              e.currentTarget.style.color = 'var(--text-tertiary)'
            }}
          >
            ✕
          </button>
        )}
      </td>
    </tr>
  )
}

// ── BlockEditor ───────────────────────────────────────────────────────────────

export function BlockEditor({ blocks, isDefault, dayLabel, saving, apiError, onChange, onSave }) {
  const { t } = useI18n()

  const validation = validateCoverage(blocks)

  // Al cambiar un campo, recalcular starts de todos los bloques siguientes
  function handleBlockChange(index, field, value) {
    const updated = blocks.map((b, i) => i === index ? { ...b, [field]: value } : { ...b })

    // Recalcular starts encadenados: start[n+1] = end[n]
    for (let j = 1; j < updated.length; j++) {
      updated[j] = { ...updated[j], start: updated[j - 1].end }
    }

    onChange(updated)
  }

  function handleRemove(index) {
    if (blocks.length <= 1) return
    const updated = blocks.filter((_, i) => i !== index)
    // Si eliminamos el primer bloque, el nuevo primero debe tener start=00:00
    if (index === 0) {
      updated[0] = { ...updated[0], start: '00:00' }
    } else {
      // Recalcular starts encadenados
      for (let j = index; j < updated.length; j++) {
        updated[j] = { ...updated[j], start: j === 0 ? '00:00' : updated[j - 1].end }
      }
    }
    onChange(updated)
  }

  function handleAddBlock() {
    const last = blocks[blocks.length - 1]
    const lastEnd = last.end

    // Si el último bloque ya termina a 24:00, ajustar su end primero
    let updatedBlocks = [...blocks]
    if (lastEnd === '24:00') {
      updatedBlocks[updatedBlocks.length - 1] = { ...last, end: '23:00' }
    }
    const newStart = updatedBlocks[updatedBlocks.length - 1].end
    updatedBlocks.push({ start: newStart, end: '24:00', mode: 'hardcore' })
    onChange(updatedBlocks)
  }

  function handleSave() {
    if (!validation.ok) return
    // Normalizar bloques: asegurarnos de que los modos van en mayúsculas para el backend
    const normalized = blocks.map(b => ({
      start: b.start,
      end: b.end,
      mode: b.mode.toUpperCase(),
    }))
    onSave(normalized)
  }

  if (!blocks) {
    return (
      <div style={{ ...cardStyle, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px', textAlign: 'center' }}>
        <p style={{ fontSize: '14px', color: 'var(--text-tertiary)' }}>
          {t('session.editor.noDay')}
        </p>
      </div>
    )
  }

  return (
    <div style={cardStyle}>
      {/* Título del editor */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <div style={{ fontSize: '15px', fontWeight: 600 }}>
          {t('session.editor.title', { day: dayLabel ?? '…' })}
        </div>
      </div>

      {/* Hint si es default */}
      {isDefault && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          padding: '8px 10px', borderRadius: 'var(--radius-sm)',
          background: 'var(--surface-2)',
          fontSize: '12px', color: 'var(--text-secondary)',
          marginBottom: '10px',
        }}>
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <circle cx="8" cy="8" r="6" />
            <path d="M8 7v4M8 5.5h.01" />
          </svg>
          {t('session.editor.defaultHint')}
        </div>
      )}

      {/* Barra de timeline en tiempo real */}
      <div style={{ marginBottom: '12px' }}>
        <TimelineBar blocks={blocks} dayLabel={dayLabel} />
      </div>

      {/* Tabla de bloques */}
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={thStyle}>{t('session.editor.from')}</th>
            <th style={thStyle}>{t('session.editor.to')}</th>
            <th style={thStyle}>{t('session.editor.mode')}</th>
            <th style={{ ...thStyle, width: '32px' }}></th>
          </tr>
        </thead>
        <tbody>
          {blocks.map((block, i) => (
            <BlockRow
              key={i}
              block={block}
              index={i}
              totalBlocks={blocks.length}
              onChange={handleBlockChange}
              onRemove={handleRemove}
            />
          ))}
        </tbody>
      </table>

      {/* Botón añadir bloque */}
      <button
        type="button"
        onClick={handleAddBlock}
        style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          padding: '6px 10px',
          border: '1px dashed var(--border-strong)',
          borderRadius: 'var(--radius-sm)',
          background: 'transparent',
          color: 'var(--text-secondary)',
          fontSize: '12px', cursor: 'pointer',
          marginTop: '8px', width: '100%',
          justifyContent: 'center',
          fontFamily: 'inherit',
          transition: 'background var(--dur-fast), color var(--dur-fast)',
        }}
        onMouseEnter={e => {
          e.currentTarget.style.background = 'var(--surface-2)'
          e.currentTarget.style.color = 'var(--text)'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.background = 'transparent'
          e.currentTarget.style.color = 'var(--text-secondary)'
        }}
      >
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M8 2v12M2 8h12" />
        </svg>
        {t('session.editor.addBlock')}
      </button>

      {/* Indicador de cobertura */}
      <TimelineCoverageIndicator validation={validation} />

      {/* Footer: error de API + botón guardar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginTop: '14px', paddingTop: '14px',
        borderTop: '1px solid var(--border)',
      }}>
        <div style={{ fontSize: '12px', color: 'var(--danger)', flex: 1 }}>
          {apiError ?? ''}
        </div>
        <button
          type="button"
          disabled={!validation.ok || saving}
          onClick={handleSave}
          aria-busy={saving}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            padding: '8px 20px',
            border: 'none', borderRadius: 'var(--radius-sm)',
            background: 'var(--btn-primary-bg)', color: 'var(--btn-primary-text)',
            fontFamily: 'inherit', fontSize: '13px', fontWeight: 600,
            cursor: (!validation.ok || saving) ? 'not-allowed' : 'pointer',
            opacity: (!validation.ok || saving) ? 0.45 : 1,
            transition: 'background var(--dur-fast)',
          }}
        >
          {saving ? <Spinner size={14} /> : null}
          {saving ? t('session.editor.saving') : t('session.editor.save')}
        </button>
      </div>
    </div>
  )
}

// ─── Estilos ──────────────────────────────────────────────────────────────────

const cardStyle = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  padding: '16px 20px',
}

const thStyle = {
  fontSize: '11px', fontWeight: 600,
  letterSpacing: '.04em', textTransform: 'uppercase',
  color: 'var(--text-secondary)',
  padding: '6px 8px',
  textAlign: 'start',
  borderBottom: '1px solid var(--border)',
  background: 'var(--surface-2)',
}
