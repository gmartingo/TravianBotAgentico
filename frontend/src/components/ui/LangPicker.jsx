/**
 * LangPicker — selector de idioma con 25 idiomas + buscador.
 *
 * - Lista idiomas por endónimo (nombre en su propia lengua).
 * - Buscador/filtro integrado (DESIGN.md §16.1: 25 es demasiado para dropdown plano).
 * - Al cambiar: fija lang, dir, persiste en localStorage.
 * - Cierre: click fuera, Escape, o selección.
 * - Patrón visual idéntico al de los mockups playground.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { Globe, Check } from 'lucide-react'
import { LANGUAGES } from '../../i18n/languages.js'
import { useI18n } from '../../i18n/index.jsx'

export function LangPicker() {
  const { lang, setLang, t } = useI18n()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const wrapRef  = useRef(null)
  const searchRef = useRef(null)

  // Filtrar idiomas por endónimo o código
  const filtered = LANGUAGES.filter((l) =>
    l.name.toLowerCase().includes(search.toLowerCase()) ||
    l.code.toLowerCase().includes(search.toLowerCase())
  )

  // Enfocar el buscador al abrir
  useEffect(() => {
    if (open && searchRef.current) {
      searchRef.current.focus()
    }
  }, [open])

  // Cerrar al hacer clic fuera
  useEffect(() => {
    if (!open) return
    function handleClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  // Cerrar con Escape
  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') {
      setOpen(false)
      setSearch('')
    }
  }, [])

  function selectLang(code) {
    setLang(code)
    setOpen(false)
    setSearch('')
  }

  const currentLang = LANGUAGES.find((l) => l.code === lang)

  return (
    <div ref={wrapRef} className="relative" onKeyDown={handleKeyDown}>
      {/* Botón disparador */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={t('topbar.selectLanguage')}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="
          appearance-none border border-[var(--border-strong)] bg-[var(--surface)]
          text-[var(--text)] h-[30px] rounded-[var(--radius-sm)]
          flex items-center gap-[6px] px-[10px] cursor-pointer
          font-[inherit] text-[13px] whitespace-nowrap
          hover:bg-[var(--surface-2)]
          transition-colors duration-[var(--dur-fast)]
          focus-visible:outline-2 focus-visible:outline-[var(--accent)]
          focus-visible:outline-offset-2
        "
      >
        <Globe size={14} className="text-[var(--text-secondary)]" aria-hidden="true" />
        <span>{currentLang?.name ?? lang}</span>
      </button>

      {/* Panel desplegable */}
      {open && (
        <div
          role="dialog"
          aria-label={t('topbar.selectLanguage')}
          className="
            absolute end-0 top-[calc(100%+8px)] w-[280px]
            max-w-[calc(100vw-32px)]
            bg-[var(--surface)] border border-[var(--border)]
            rounded-[var(--radius-md)] shadow-[var(--shadow-lg)]
            overflow-hidden z-[200]
          "
        >
          {/* Buscador */}
          <div className="p-[10px] border-b border-[var(--border)]">
            <input
              ref={searchRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('topbar.searchLanguage')}
              className="
                w-full h-8 border border-[var(--border-strong)]
                bg-[var(--surface-2)] text-[var(--text)]
                rounded-[var(--radius-sm)] px-[10px]
                font-[inherit] text-[13px]
                placeholder:text-[var(--text-tertiary)]
                focus-visible:outline-none
                focus-visible:border-[var(--accent)]
                focus-visible:ring-2 focus-visible:ring-[var(--accent)]
                focus-visible:ring-offset-0
              "
            />
          </div>

          {/* Lista de idiomas */}
          <ul
            role="listbox"
            aria-label={t('topbar.selectLanguage')}
            className="max-h-[280px] overflow-y-auto p-[6px]"
          >
            {filtered.length === 0 && (
              <li className="px-3 py-2 text-[13px] text-[var(--text-tertiary)] text-center">
                —
              </li>
            )}
            {filtered.map((l) => {
              const selected = l.code === lang
              return (
                <li key={l.code} role="option" aria-selected={selected}>
                  <button
                    type="button"
                    onClick={() => selectLang(l.code)}
                    className={`
                      flex items-center justify-between gap-[10px] w-full
                      px-[10px] py-2 rounded-[var(--radius-sm)] cursor-pointer
                      border-none font-[inherit] text-[13px] text-start
                      transition-colors duration-[var(--dur-fast)]
                      ${selected
                        ? 'bg-[var(--accent-subtle)] text-[var(--accent-text)] font-semibold'
                        : 'bg-transparent text-[var(--text)] hover:bg-[var(--surface-2)]'
                      }
                    `}
                  >
                    <span
                      // dir explícito por ítem para que árabe/hebreo/persa
                      // se rendericen correctamente dentro del panel LTR
                      dir={l.rtl ? 'rtl' : 'ltr'}
                      lang={l.code}
                    >
                      {l.name}
                    </span>
                    <span className={`
                      font-mono text-[11px] uppercase tracking-[0.04em]
                      ${selected ? 'text-[var(--accent-text)]' : 'text-[var(--text-tertiary)]'}
                    `}>
                      {selected
                        ? <Check size={12} aria-hidden="true" />
                        : l.code}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
