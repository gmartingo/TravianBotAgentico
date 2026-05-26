/**
 * WorldSpacePage — placeholder S9 Espacio del mundo (Etapa 1).
 *
 * Sin sidebar de gestión (ruta fuera del ManagementShell).
 * Tiene su propia Topbar mínima con "← Mundos".
 * Contenido real se implementa en Etapa 2.
 */
import { useNavigate } from 'react-router-dom'
import { ThemeToggle } from '../components/ui/ThemeToggle.jsx'
import { LangPicker } from '../components/ui/LangPicker.jsx'
import { useI18n } from '../i18n/index.jsx'

export function WorldSpacePage() {
  const navigate = useNavigate()
  const { t } = useI18n()

  return (
    <div className="flex flex-col h-full bg-[var(--bg)]">
      {/* ── Topbar mínima de S9 (sin sidebar) ── */}
      <header
        className="
          flex items-center gap-3 px-5 h-[52px] flex-shrink-0
          bg-[var(--surface)] border-b border-[var(--border)]
          z-50
        "
        role="banner"
      >
        {/* Botón "← Mundos" (ghost-accent) */}
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="
            appearance-none border-none bg-transparent
            text-[var(--accent-text)] hover:text-[var(--accent-hover)]
            flex items-center gap-1 text-[13px] font-medium cursor-pointer
            focus-visible:outline-2 focus-visible:outline-[var(--accent)]
            focus-visible:outline-offset-2 rounded-[var(--radius-sm)]
            px-1 py-1
            transition-colors duration-[var(--dur-fast)]
          "
          aria-label={t('topbar.backToWorlds')}
        >
          {/* El texto ya incluye la flecha orientada por idioma (← / →). Sin icono extra. */}
          <span>{t('topbar.backToWorlds')}</span>
        </button>

        {/* Separador hairline */}
        <div
          className="w-px h-5 bg-[var(--border)] flex-shrink-0"
          aria-hidden="true"
        />

        {/* Wordmark */}
        <div className="flex items-center gap-2 font-semibold text-[15px]">
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
          <span className="hidden sm:inline">{t('app.name')}</span>
        </div>

        {/* Grow */}
        <div className="flex-1" />

        {/* Controles */}
        <ThemeToggle />
        <LangPicker />
      </header>

      {/* Contenido del mundo: AÚN SIN DISEÑAR. Por ahora solo la vuelta atrás. */}
      <main className="flex-1 overflow-y-auto" />
    </div>
  )
}
