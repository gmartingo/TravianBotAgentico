/**
 * App — raíz de la aplicación.
 *
 * Árbol de rutas (React Router v6):
 *
 * /                       → redirige a /cuentas
 * /cuentas                → ManagementShell > AccountsListPage   (S2)
 * /cuentas/:id            → ManagementShell > AccountDetailPage  (S4)
 * /mundos/:worldId        → WorldSpacePage                       (S9, sin sidebar)
 * *                       → NotFound
 *
 * El ManagementShell (topbar + sidebar Cuentas) NO se renderiza en S9.
 * El modo Gestión (S1–S8) y el Espacio del mundo (S9) son shells distintos.
 */
import { Routes, Route, Navigate } from 'react-router-dom'
import { ManagementShell } from './components/layout/ManagementShell.jsx'
import { AccountsListPage }  from './pages/AccountsListPage.jsx'
import { AccountDetailPage } from './pages/AccountDetailPage.jsx'
import { WorldSpacePage }    from './pages/WorldSpacePage.jsx'

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
      <p className="text-[var(--text-secondary)] text-[14px]">404 — Página no encontrada</p>
      <a href="/cuentas" className="text-[var(--accent-text)] text-[13px]">
        ← Volver al inicio
      </a>
    </div>
  )
}

export function App() {
  return (
    <Routes>
      {/* ── Modo Gestión (con topbar + sidebar) ──────── */}
      <Route element={<ManagementShell />}>
        <Route index element={<Navigate to="/cuentas" replace />} />
        <Route path="/cuentas"     element={<AccountsListPage />} />
        <Route path="/cuentas/:id" element={<AccountDetailPage />} />
      </Route>

      {/* ── Espacio del mundo (sin sidebar) ──────────── */}
      <Route path="/mundos/:worldId" element={<WorldSpacePage />} />

      {/* ── 404 ───────────────────────────────────────── */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
