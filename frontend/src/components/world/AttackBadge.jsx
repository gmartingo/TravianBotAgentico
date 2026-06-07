/**
 * AttackBadge — badge compacto de peligro "N ataques entrantes".
 *
 * Spec:  docs/design/aviso-ataque-mundos.md §6.1 — Nivel 1
 * Usado en AccountDetailPage (celda Sesión), junto al SessionStatusBadge.
 *
 * Props:
 *   count {number}  — número de ataques. Solo se renderiza cuando count >= 1.
 *   t     {func}    — función de traducción useI18n()
 *
 * Diseño (spec §6.1):
 *   - Icono ShieldAlert 12px, color var(--danger), aria-hidden
 *   - Número 11px, font-mono, var(--danger)
 *   - Fondo: color-mix(in srgb, var(--danger) 10%, transparent)
 *   - Borde: 1px solid color-mix(in srgb, var(--danger) 25%, transparent)
 *   - Padding: 2px 6px, border-radius: var(--radius-full)
 *   - aria-label dinámico con el conteo (spec §9 radar.badge.aria_*)
 *
 * Accesibilidad:
 *   - No solo color: icono + número (spec §10).
 *   - aria-label describe el conteo en texto plano.
 *   - role="status" para que el screen reader lo anuncie como dato de estado.
 *
 * Prioridad responsive: P1 — nunca se oculta en móvil (spec §11).
 */

function IconShieldAlert({ size = 12 }) {
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
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  )
}

/**
 * AttackBadge — renderiza solo cuando count >= 1.
 */
export function AttackBadge({ count, t }) {
  if (!count || count < 1) return null

  const ariaLabel = count === 1
    ? t('radar.badge.aria_one')
    : t('radar.badge.aria_other', { count })

  return (
    <span
      role="status"
      aria-label={ariaLabel}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '3px',
        padding: '2px 6px',
        borderRadius: 'var(--radius-full)',
        background: 'color-mix(in srgb, var(--danger) 10%, transparent)',
        border: '1px solid color-mix(in srgb, var(--danger) 25%, transparent)',
        color: 'var(--danger)',
        fontSize: '11px',
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
        fontWeight: 500,
        lineHeight: 1,
        flexShrink: 0,
        whiteSpace: 'nowrap',
      }}
    >
      <IconShieldAlert size={12} />
      <span aria-hidden="true">{count}</span>
    </span>
  )
}
