/**
 * ManagementShell — contenedor del modo Gestión.
 * Layout: Topbar (100% ancho) + body (Sidebar + Outlet).
 *
 * Responsive (DESIGN.md §17 / spec §11):
 *   ≥ lg (1024px): sidebar fija 200px.
 *   md (768–1023px): sidebar colapsada 48px (solo iconos).
 *   < md: sidebar oculta (drawer pendiente para etapas siguientes).
 *
 * El Outlet renderiza las rutas de gestión: /cuentas, /cuentas/:id.
 */
import { Outlet } from 'react-router-dom'
import { Topbar } from './Topbar.jsx'
import { Sidebar } from './Sidebar.jsx'
import { useWindowSize } from '../../hooks/useWindowSize.js'

export function ManagementShell() {
  const { width } = useWindowSize()
  // md breakpoint = 768, lg = 1024
  const showSidebar  = width >= 768
  const collapseSidebar = width < 1024

  return (
    <div className="flex flex-col h-full">
      <Topbar />
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {showSidebar && <Sidebar collapsed={collapseSidebar} />}
        <main
          id="main-content"
          className="flex-1 overflow-y-auto"
          tabIndex={-1}
          aria-label="Contenido principal"
        >
          <Outlet />
        </main>
      </div>
    </div>
  )
}
