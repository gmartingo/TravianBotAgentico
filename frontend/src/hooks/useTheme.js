/**
 * useTheme — gestiona el tema claro/oscuro.
 *
 * Precedencia:
 *   1. localStorage['theme'] ("light" | "dark") — override manual
 *   2. prefers-color-scheme — preferencia del sistema
 *
 * El toggle persiste en localStorage y fija data-theme en <html>.
 * El script en index.html aplica el tema antes del primer render (sin FOUC).
 */
import { useState, useEffect, useCallback } from 'react'

function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function getInitialTheme() {
  const stored = localStorage.getItem('theme')
  if (stored === 'light' || stored === 'dark') return stored
  return getSystemTheme()
}

export function useTheme() {
  const [theme, setThemeState] = useState(getInitialTheme)

  // Aplicar data-theme en <html> cada vez que cambia
  useEffect(() => {
    const root = document.documentElement
    // Si coincide con el sistema y no hay override, eliminamos data-theme
    // para que el @media (prefers-color-scheme) funcione libre.
    const system = getSystemTheme()
    const stored = localStorage.getItem('theme')

    if (stored === theme) {
      // override manual activo
      root.dataset.theme = theme
    } else {
      // no hay override — dejar que el sistema mande
      delete root.dataset.theme
    }
  }, [theme])

  // Escuchar cambios del sistema (si no hay override manual)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e) => {
      const stored = localStorage.getItem('theme')
      if (!stored) {
        setThemeState(e.matches ? 'dark' : 'light')
      }
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  const setTheme = useCallback((t) => {
    localStorage.setItem('theme', t)
    document.documentElement.dataset.theme = t
    setThemeState(t)
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'dark' ? 'light' : 'dark')
  }, [theme, setTheme])

  return { theme, setTheme, toggleTheme }
}
