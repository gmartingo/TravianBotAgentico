/**
 * PathTestResultPanel — Panel inline expandible de resultado del test EP-N14.
 *
 * Muestra el reporte de la ruta paso a paso:
 *  - Estado OK: chip verde "Ruta OK" + duración + pasos en verde + URL alcanzada + browser_note
 *  - Estado ERROR: chip rojo "Falló en el paso N" + pasos ok/error/no-ejecutado + motivo + browser_note
 *
 * Props:
 *  - result        {object}   — PathTestResponse del backend (overall, steps, aborted_at_step, browser_note)
 *  - pathSteps     {Array}    — path.steps de la ruta (para inferir pasos no ejecutados)
 *  - durationMs    {number}   — calculado en el frontend (Date.now() antes/después del POST)
 *  - onClose       {Function} — callback para cerrar el panel; el foco vuelve al botón "Probar"
 *
 * Spec: docs/design/noise-catalog-ui.md §6 (PathTestResultPanel), §7, §8, §10, §12
 * CA: CA-PT01..CA-PT18 (docs/design/noise-catalog-ui.md §13)
 */
import { useI18n } from '../../../i18n/index.jsx'

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Formatea una duración en ms.
 * < 1000 ms → "842 ms"
 * ≥ 1000 ms → "3.2 s"
 * Spec §12: font-mono tabular-nums.
 */
function formatMs(ms) {
  if (ms == null || isNaN(ms)) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

// ── Icono información ─────────────────────────────────────────────────────────
function IconInfo({ size = 12 }) {
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
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="8" strokeWidth="3" strokeLinecap="round" />
      <line x1="12" y1="12" x2="12" y2="16" />
    </svg>
  )
}

// ── Fila de paso ejecutado (ok o error) ───────────────────────────────────────
function ExecutedStepRow({ step }) {
  const isOk = step.status === 'ok'
  return (
    <div style={{
      borderBottom: '1px solid var(--border)',
      padding: '4px 0',
    }}>
      {/* Línea principal: icono + número + acción + selector + URL */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        fontSize: '12px',
        flexWrap: 'nowrap',
      }}>
        {/* Icono estado */}
        <span style={{
          color: isOk ? 'var(--success)' : 'var(--danger)',
          flexShrink: 0,
          width: '14px',
          textAlign: 'center',
          fontWeight: 700,
        }}>
          {isOk ? '✓' : '✕'}
        </span>

        {/* Número de paso */}
        <span style={{
          fontFamily: 'var(--font-mono)',
          color: 'var(--text-tertiary)',
          fontSize: '11px',
          width: '16px',
          textAlign: 'right',
          flexShrink: 0,
        }}>
          {step.step_order}
        </span>

        {/* Badge de acción */}
        <span style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-full)',
          padding: '0 5px',
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          color: 'var(--text-secondary)',
          flexShrink: 0,
          whiteSpace: 'nowrap',
        }}>
          {step.action}
        </span>

        {/* Selector */}
        <code style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '11px',
          flex: 1,
          wordBreak: 'break-all',
          color: isOk ? 'var(--text)' : 'var(--text-secondary)',
          minWidth: 0,
        }}>
          {step.selector}
        </code>

        {/* URL alcanzada (solo si status ok y current_url presente) */}
        {isOk && step.current_url && (
          <span
            title={step.current_url}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              color: 'var(--text-tertiary)',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              maxWidth: '180px',
              flexShrink: 0,
            }}
          >
            → {step.current_url}
          </span>
        )}
      </div>

      {/* Para el paso con error: motivo en segunda línea + URL antes del intento */}
      {!isOk && (
        <div style={{
          paddingInlineStart: 'calc(14px + 16px + 6px + 6px)',
          marginTop: '3px',
          display: 'flex',
          flexDirection: 'column',
          gap: '2px',
        }}>
          {step.reason && (
            <span style={{
              fontSize: '11px',
              color: 'var(--danger)',
            }}>
              {step.reason}
            </span>
          )}
          {step.current_url && (
            <span
              title={step.current_url}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                color: 'var(--text-tertiary)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: '220px',
              }}
            >
              → {step.current_url}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// ── Fila de paso no ejecutado ─────────────────────────────────────────────────
function NotRunStepRow({ stepOrder, action, selector, t }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
      fontSize: '12px',
      padding: '4px 0',
      borderBottom: '1px solid var(--border)',
      opacity: 0.45,
    }}>
      {/* Icono dash */}
      <span style={{
        color: 'var(--text-disabled)',
        flexShrink: 0,
        width: '14px',
        textAlign: 'center',
      }}>
        ─
      </span>

      {/* Número */}
      <span style={{
        fontFamily: 'var(--font-mono)',
        color: 'var(--text-disabled)',
        fontSize: '11px',
        width: '16px',
        textAlign: 'right',
        flexShrink: 0,
      }}>
        {stepOrder}
      </span>

      {/* Badge acción */}
      {action && (
        <span style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-full)',
          padding: '0 5px',
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          color: 'var(--text-disabled)',
          flexShrink: 0,
          whiteSpace: 'nowrap',
        }}>
          {action}
        </span>
      )}

      {/* Selector */}
      {selector && (
        <code style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '11px',
          flex: 1,
          color: 'var(--text-disabled)',
          wordBreak: 'break-all',
          minWidth: 0,
        }}>
          {selector}
        </code>
      )}

      {/* Etiqueta "no ejecutado" */}
      <span style={{
        fontSize: '10px',
        color: 'var(--text-disabled)',
        fontStyle: 'italic',
        flexShrink: 0,
      }}>
        {t('noise.test.stepNotRun')}
      </span>
    </div>
  )
}

// ── Componente principal ──────────────────────────────────────────────────────
export function PathTestResultPanel({ result, pathSteps, durationMs, onClose, closeRef }) {
  const { t } = useI18n()

  if (!result) return null

  const { overall, steps: executedSteps = [], aborted_at_step, browser_note } = result
  const isOk = overall === 'ok'

  // Pasos no ejecutados: los definidos en pathSteps con step_order > aborted_at_step
  // y que no aparecen en executedSteps. Solo aplica si overall === 'error'.
  const executedOrders = new Set(executedSteps.map(s => s.step_order))
  const notRunSteps = (!isOk && aborted_at_step != null)
    ? (pathSteps ?? []).filter(s => !executedOrders.has(s.step_order) && s.step_order > aborted_at_step)
    : []

  return (
    <div
      role="region"
      aria-label={t('noise.test.resultLabel')}
      style={{
        background: 'var(--surface-2)',
        borderTop: '1px solid var(--border)',
        padding: '10px 12px',
      }}
    >
      {/* Header: chip resultado + duración + botón cerrar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        marginBottom: '8px',
      }}>
        {/* Chip overall */}
        <span style={{
          background: isOk ? 'rgba(36,138,61,.10)' : 'rgba(201,53,44,.10)',
          color: isOk ? 'var(--success)' : 'var(--danger)',
          borderRadius: 'var(--radius-full)',
          padding: '2px 8px',
          fontSize: '12px',
          fontWeight: 600,
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          flexShrink: 0,
        }}>
          {isOk
            ? `✓ ${t('noise.test.resultOk')}`
            : `✕ ${t('noise.test.resultError').replace('{n}', aborted_at_step ?? '?')}`
          }
        </span>

        {/* Duración */}
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontVariantNumeric: 'tabular-nums',
          fontSize: '12px',
          color: 'var(--text-tertiary)',
          flexShrink: 0,
        }}>
          {formatMs(durationMs)}
        </span>

        {/* Spacer */}
        <span style={{ flex: 1 }} />

        {/* Botón cerrar */}
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          aria-label={t('noise.test.closeResult')}
          style={{
            appearance: 'none',
            border: '1px solid var(--border)',
            background: 'transparent',
            color: 'var(--text-secondary)',
            borderRadius: 'var(--radius-sm)',
            padding: '2px 8px',
            fontSize: '11px',
            cursor: 'pointer',
            fontFamily: 'inherit',
            flexShrink: 0,
          }}
        >
          {t('noise.test.closeResult')}
        </button>
      </div>

      {/* Separador */}
      <hr style={{ margin: '0 0 8px', border: 'none', borderTop: '1px solid var(--border)' }} />

      {/* Lista de pasos ejecutados */}
      {executedSteps.length === 0 && notRunSteps.length === 0 && (
        <p style={{ fontSize: '12px', color: 'var(--text-tertiary)', margin: '4px 0 8px' }}>
          {/* Ruta sin pasos — overall siempre ok */}
          —
        </p>
      )}

      {executedSteps.map((step) => (
        <ExecutedStepRow
          key={step.step_order}
          step={step}
        />
      ))}

      {notRunSteps.map((step) => (
        <NotRunStepRow
          key={step.step_order}
          stepOrder={step.step_order}
          action={step.action}
          selector={step.selector}
          t={t}
        />
      ))}

      {/* Footer: browser_note */}
      {browser_note && (
        <div style={{
          marginTop: '8px',
          paddingTop: '8px',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          gap: '6px',
          alignItems: 'flex-start',
          fontSize: '11px',
          color: 'var(--text-tertiary)',
          fontStyle: 'italic',
        }}>
          <IconInfo size={12} />
          <span>{browser_note}</span>
        </div>
      )}
    </div>
  )
}
