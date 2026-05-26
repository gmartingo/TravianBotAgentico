/**
 * Catálogo de los 25 idiomas soportados por el backend.
 * Códigos = los de kirilloid / SUPPORTED_LANGUAGES en core/i18n/languages.py.
 * Nombres = endónimos (nombre en la propia lengua) tal como exige DESIGN.md §16.1.
 * RTL = true para árabe, hebreo y persa.
 */
export const LANGUAGES = [
  { code: 'ar', name: 'العربية',    rtl: true  },
  { code: 'bg', name: 'Български',  rtl: false },
  { code: 'cs', name: 'Čeština',    rtl: false },
  { code: 'da', name: 'Dansk',      rtl: false },
  { code: 'de', name: 'Deutsch',    rtl: false },
  { code: 'el', name: 'Ελληνικά',   rtl: false },
  { code: 'en', name: 'English',    rtl: false },
  { code: 'es', name: 'Español',    rtl: false },
  { code: 'fa', name: 'فارسی',      rtl: true  },
  { code: 'fr', name: 'Français',   rtl: false },
  { code: 'he', name: 'עברית',      rtl: true  },
  { code: 'hu', name: 'Magyar',     rtl: false },
  { code: 'it', name: 'Italiano',   rtl: false },
  { code: 'ja', name: '日本語',       rtl: false },
  { code: 'lt', name: 'Lietuvių',   rtl: false },
  { code: 'lv', name: 'Latviešu',   rtl: false },
  { code: 'nl', name: 'Nederlands', rtl: false },
  { code: 'pl', name: 'Polski',     rtl: false },
  { code: 'pt', name: 'Português',  rtl: false },
  { code: 'rs', name: 'Srpski',     rtl: false },
  { code: 'ru', name: 'Русский',    rtl: false },
  { code: 'sl', name: 'Slovenščina',rtl: false },
  { code: 'sv', name: 'Svenska',    rtl: false },
  { code: 'tr', name: 'Türkçe',     rtl: false },
  { code: 'uk', name: 'Українська', rtl: false },
]

export const RTL_LANGS = LANGUAGES.filter((l) => l.rtl).map((l) => l.code)

export function isRTL(code) {
  return RTL_LANGS.includes(code)
}

export function getLang(code) {
  return LANGUAGES.find((l) => l.code === code) || LANGUAGES.find((l) => l.code === 'es')
}
