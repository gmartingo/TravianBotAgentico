/**
 * NewAccountPage — Ruta /cuentas/nueva.
 *
 * Renderiza la lista de cuentas (S2) como fondo y, encima,
 * el wizard modal (S3) centrado con backdrop.
 *
 * El shell (Topbar + Sidebar) permanece visible detrás del backdrop,
 * exactamente como en el mockup aprobado (wizard.playground.html).
 *
 * Al cerrar el wizard (cancelar, ESC, click fuera, o éxito),
 * WizardModal navega internamente a /cuentas o a /cuentas/:id.
 */
import { useRef } from 'react'
import { AccountsListPage } from './AccountsListPage.jsx'
import { WizardModal }      from '../components/ui/WizardModal.jsx'

export function NewAccountPage() {
  // Ref del trigger (botón "Nueva cuenta" en AccountsListPage no es
  // fácilmente accesible desde aquí). Pasamos null; WizardModal lo gestiona
  // con null-check para no lanzar error.
  const triggerRef = useRef(null)

  return (
    <>
      {/* Lista de cuentas como fondo (el backdrop del wizard la atenúa) */}
      <AccountsListPage />

      {/* Wizard en capa superior */}
      <WizardModal triggerRef={triggerRef} />
    </>
  )
}
