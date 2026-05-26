/**
 * Topbar — barra superior persistente en el modo Gestión.
 * Contiene: wordmark TravianBot | grow | ThemeToggle | LangPicker.
 * Hereda visualmente los tokens exactos del mockup cuentas.playground.html.
 */
import { ThemeToggle } from '../ui/ThemeToggle.jsx'
import { LangPicker } from '../ui/LangPicker.jsx'
import { useI18n } from '../../i18n/index.jsx'

export function Topbar() {
  const { t } = useI18n()

  return (
    <header
      className="
        flex items-center gap-3 px-5 h-[52px] flex-shrink-0
        bg-[var(--surface)] border-b border-[var(--border)]
        z-50
      "
      role="banner"
    >
      {/* Wordmark */}
      <div className="flex items-center gap-2 font-semibold text-[15px]" aria-label={t('app.name')}>
        {/* Logo: cuadrado grafito/plata con "TB" */}
        <div
          className="
            w-7 h-7 rounded-[7px] grid place-items-center
            font-bold text-[12px] flex-shrink-0
            bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)]
          "
          aria-hidden="true"
        >
          TB
        </div>
        {/* Texto "TravianBot" — se oculta en móvil muy pequeño (P3) */}
        <span className="hidden sm:inline">{t('app.name')}</span>
      </div>

      {/* Grow */}
      <div className="flex-1" />

      {/* Controles */}
      <ThemeToggle />
      <LangPicker />
    </header>
  )
}
