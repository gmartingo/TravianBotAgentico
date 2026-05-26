/**
 * uiUtils.jsx — Utilidades de UI compartidas entre componentes del proyecto.
 *
 * Exporta:
 *  - parseServerUrl(raw)   → "ts1 · x1 · international" | null
 *  - isValidServerUrl(raw) → boolean
 *  - Spinner               → SVG animado inline (mismo estilo que WizardModal)
 *  - useFocusTrap(ref, active) → hook de focus trap para modales
 *  - FOCUSABLE             → selector de elementos focusables
 *
 * Convención de tamaños: igual que el mockup aprobado (cuenta-detalle.playground.html).
 */
import { useEffect } from 'react'

// ─── parseServerUrl ──────────────────────────────────────────────────────────
// https://ts1.x1.international.travian.com/ → "ts1 · x1 · international"
// Si no parseable → null (mostrar "—" en --text-tertiary)
export function parseServerUrl(raw) {
  if (!raw || typeof raw !== 'string') return null
  let hostname
  try {
    const normalised = raw.match(/^https?:\/\//) ? raw : `https://${raw}`
    hostname = new URL(normalised).hostname
  } catch {
    return null
  }
  const parts = hostname.split('.')
  if (parts.length < 3) return null
  const server = parts[0]
  const speed  = parts.find(p => /^x\d+$/i.test(p)) ?? null
  const travianIdx = parts.findIndex(p => p.toLowerCase() === 'travian')
  const region = parts
    .slice(1, travianIdx < 0 ? parts.length - 1 : travianIdx)
    .find(p => !/^x\d+$/i.test(p) && p !== server) ?? null
  if (!server) return null
  return [server, speed, region].filter(Boolean).join(' · ')
}

// ─── isValidServerUrl ────────────────────────────────────────────────────────
export function isValidServerUrl(raw) {
  if (!raw) return false
  try {
    if (!raw.match(/^https?:\/\//)) return false
    new URL(raw)
    return true
  } catch {
    return false
  }
}

// ─── Spinner ─────────────────────────────────────────────────────────────────
export function Spinner({ size = 14, className = '' }) {
  return (
    <svg
      width={size} height={size}
      viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" aria-hidden="true"
      className={className}
      style={{ animation: 'spin 0.6s linear infinite', flexShrink: 0 }}
    >
      <path d="M12 2a10 10 0 0 1 10 10" />
    </svg>
  )
}

// ─── Spinner pequeño para badges (11px) ─────────────────────────────────────
export function BadgeSpinner() {
  return (
    <span
      aria-hidden="true"
      style={{
        width: '11px', height: '11px',
        border: '1.8px solid currentColor', borderTopColor: 'transparent',
        borderRadius: '50%', display: 'inline-block', flexShrink: 0,
        animation: 'spin 0.7s linear infinite',
      }}
    />
  )
}

// ─── FOCUSABLE selector ──────────────────────────────────────────────────────
export const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([readonly])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

// ─── useFocusTrap ────────────────────────────────────────────────────────────
export function useFocusTrap(ref, active) {
  useEffect(() => {
    if (!active || !ref.current) return
    const el = ref.current
    const focusable = () => Array.from(el.querySelectorAll(FOCUSABLE))

    function handler(e) {
      if (e.key !== 'Tab') return
      const nodes = focusable()
      if (!nodes.length) return
      const first = nodes[0]
      const last  = nodes[nodes.length - 1]
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus() }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [ref, active])
}

// ─── Toast global ────────────────────────────────────────────────────────────
// Crea un nodo de toast DOM si no existe y lo muestra 3s.
let toastTimer = null
export function showToast(msg) {
  let el = document.getElementById('__travianbot-toast')
  if (!el) {
    el = document.createElement('div')
    el.id = '__travianbot-toast'
    el.setAttribute('role', 'status')
    el.setAttribute('aria-live', 'polite')
    Object.assign(el.style, {
      position: 'fixed',
      insetInline: '0',
      bottom: '24px',
      margin: 'auto',
      width: 'max-content',
      maxWidth: '90vw',
      background: 'var(--btn-primary-bg)',
      color: 'var(--btn-primary-text)',
      padding: '10px 16px',
      borderRadius: 'var(--radius-sm)',
      boxShadow: 'var(--shadow-lg)',
      fontSize: '13px',
      zIndex: '500',
      pointerEvents: 'none',
      transition: 'opacity var(--dur-base) var(--ease), transform var(--dur-base) var(--ease)',
      opacity: '0',
      transform: 'translateY(8px)',
    })
    document.body.appendChild(el)
  }
  el.textContent = msg
  el.style.opacity = '1'
  el.style.transform = 'translateY(0)'
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    el.style.opacity = '0'
    el.style.transform = 'translateY(8px)'
  }, 3000)
}
