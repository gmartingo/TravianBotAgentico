/**
 * Punto de entrada de la aplicación React.
 * Monta: BrowserRouter > I18nProvider > App.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { I18nProvider } from './i18n/index.jsx'
import { App } from './App.jsx'

// Estilos globales (tokens CSS + reset + Tailwind v4)
import './styles/app.css'

const container = document.getElementById('root')

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <App />
      </I18nProvider>
    </BrowserRouter>
  </StrictMode>
)
