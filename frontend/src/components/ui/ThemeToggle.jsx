/**
 * ThemeToggle — botón ícono ☀/🌙 para cambiar el tema.
 * Patrón idéntico al de los mockups: mismo tamaño, mismo color, mismo SVG.
 * Usa useTheme() + useI18n() para el aria-label.
 */
import { Sun, Moon } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme.js'
import { useI18n } from '../../i18n/index.jsx'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const { t } = useI18n()
  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={t('topbar.toggleTheme')}
      title={t('topbar.toggleTheme')}
      className="
        appearance-none border border-[var(--border)] bg-transparent
        text-[var(--text-secondary)] w-8 h-8 rounded-[var(--radius-sm)]
        grid place-items-center cursor-pointer
        hover:bg-[var(--surface-2)] hover:text-[var(--text)]
        transition-colors duration-[var(--dur-fast)]
        focus-visible:outline-2 focus-visible:outline-[var(--accent)]
        focus-visible:outline-offset-2
      "
    >
      {isDark
        ? <Sun  size={16} aria-hidden="true" />
        : <Moon size={16} aria-hidden="true" />}
    </button>
  )
}
