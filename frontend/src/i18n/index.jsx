/**
 * Sistema i18n del dashboard TravianBot.
 *
 * Uso:
 *   const { t, lang, setLang } = useI18n()
 *   t('nav.accounts')                     → "Cuentas"
 *   t('wizard.step', { current: 1, total: 2 }) → "Paso 1 de 2"
 *   t('page.accounts.caption', { n: 3 })  → usa .pl si n≠1
 *
 * Fallback:
 *   Si la clave no existe en el idioma activo, cae al catálogo 'es'.
 *   Si tampoco existe en 'es', devuelve la propia clave (nunca undefined).
 *
 * RTL:
 *   Al cambiar idioma se aplica dir="rtl|ltr" y lang="<code>" en <html>.
 *   Persistido en localStorage['lang'].
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import CATALOG from './catalog/index.js'
import { isRTL } from './languages.js'

const DEFAULT_LANG = 'es'
const FALLBACK_LANG = 'es'

function getStoredLang() {
  const stored = localStorage.getItem('lang')
  return CATALOG[stored] ? stored : DEFAULT_LANG
}

/** Aplica lang y dir al elemento <html> */
function applyLangToDOM(code) {
  const root = document.documentElement
  root.lang = code
  root.dir = isRTL(code) ? 'rtl' : 'ltr'
}

/** Interpola {variable} en un string de traducción */
function interpolate(str, vars) {
  if (!vars || typeof str !== 'string') return str
  return str.replace(/\{(\w+)\}/g, (_, key) =>
    vars[key] !== undefined ? vars[key] : `{${key}}`
  )
}

// ── Función de traducción (sin React, útil para utils) ───────
export function translate(catalog, lang, key, vars) {
  const active = catalog[lang] || {}
  const fallback = catalog[FALLBACK_LANG] || {}

  // Para plurales: si hay {n} y existe clave `.pl`, usarla cuando n ≠ 1
  let resolved
  if (vars && vars.n !== undefined && vars.n !== 1 && active[key + '.pl']) {
    resolved = active[key + '.pl']
  } else if (vars && vars.n !== undefined && vars.n !== 1 && fallback[key + '.pl']) {
    resolved = fallback[key + '.pl']
  } else {
    resolved = active[key] ?? fallback[key] ?? key
  }

  return interpolate(resolved, vars)
}

// ── Context ───────────────────────────────────────────────────
const I18nContext = createContext(null)

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(getStoredLang)

  // Aplicar al DOM en el mount y en cada cambio de idioma
  useEffect(() => {
    applyLangToDOM(lang)
  }, [lang])

  const setLang = useCallback((code) => {
    if (!CATALOG[code]) return
    localStorage.setItem('lang', code)
    applyLangToDOM(code)
    setLangState(code)
  }, [])

  const t = useCallback(
    (key, vars) => translate(CATALOG, lang, key, vars),
    [lang]
  )

  return (
    <I18nContext.Provider value={{ t, lang, setLang }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n debe usarse dentro de <I18nProvider>')
  return ctx
}
