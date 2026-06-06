/**
 * Sidebar — navegación vertical del modo Gestión.
 *
 * Desktop (≥lg): fija 200px.
 * Tablet (md): icono-only 48px (colapsada).
 * Móvil (<md): se gestiona desde MobileDrawer (fuera del scope Etapa 1).
 *              En esta etapa, en móvil simplemente no se muestra el sidebar.
 *
 * Ítems activos: acento oro + borde start 3px + fondo accent-subtle.
 * Ítems disabled: text-disabled + cursor not-allowed + tooltip "Próximamente".
 */
import { NavLink } from 'react-router-dom'
import { Users, Calculator, Swords, BookOpen } from 'lucide-react'
import { useI18n } from '../../i18n/index.jsx'

// "Cuentas", la "Calculadora", los "Reportes de oasis" y el "Catálogo de rutas"
// viven en el shell de gestión: son herramientas independientes del mundo.
const NAV_ITEMS = [
  {
    key: 'accounts',
    to: '/cuentas',
    icon: Users,
    labelKey: 'nav.accounts',
    disabled: false,
  },
  {
    key: 'calculator',
    to: '/calculadora',
    icon: Calculator,
    labelKey: 'worldnav.calculator',
    disabled: false,
  },
  {
    key: 'attack-reports',
    to: '/reportes-oasis',
    icon: Swords,
    labelKey: 'nav.attackReports',
    disabled: false,
  },
  {
    key: 'route-templates',
    to: '/rutas',
    icon: BookOpen,
    labelKey: 'nav.routeTemplates',
    disabled: false,
  },
]

function SidebarItem({ item, collapsed }) {
  const { t } = useI18n()
  const label = t(item.labelKey)
  const soon  = t('nav.comingSoon')

  const baseClass = `
    relative flex items-center gap-[10px] px-[10px] py-2
    rounded-[var(--radius-sm)] w-full text-start
    font-[inherit] text-[14px] border-none cursor-pointer
    transition-colors duration-[var(--dur-fast)]
  `

  if (item.disabled) {
    return (
      <button
        type="button"
        disabled
        title={soon}
        aria-label={`${label} — ${soon}`}
        className={`${baseClass} text-[var(--text-disabled)] cursor-not-allowed bg-transparent`}
      >
        <item.icon size={16} className="flex-shrink-0" aria-hidden="true" />
        {!collapsed && (
          <>
            <span className="flex-1">{label}</span>
            <span className="text-[10px] font-mono uppercase tracking-[0.04em] text-[var(--text-disabled)]">
              {soon}
            </span>
          </>
        )}
      </button>
    )
  }

  return (
    <NavLink
      to={item.to}
      end={item.to === '/cuentas'}
      className={({ isActive }) => `
        ${baseClass}
        ${isActive
          ? 'bg-[var(--accent-subtle)] text-[var(--accent-text)] font-medium'
          : 'bg-transparent text-[var(--text)] hover:bg-[var(--surface-2)]'
        }
      `}
      aria-label={collapsed ? label : undefined}
    >
      {({ isActive }) => (
        <>
          {/* Barra de acento en el borde start (solo activo) */}
          {isActive && (
            <span
              aria-hidden="true"
              className="
                absolute inset-y-1 start-0
                w-[3px] rounded-[var(--radius-full)] bg-[var(--accent)]
              "
            />
          )}
          <item.icon
            size={16}
            className="flex-shrink-0"
            aria-hidden="true"
          />
          {!collapsed && <span className="flex-1">{label}</span>}
        </>
      )}
    </NavLink>
  )
}

export function Sidebar({ collapsed = false }) {
  const { t } = useI18n()

  return (
    <aside
      className={`
        flex-shrink-0 bg-[var(--surface)]
        border-e border-[var(--border)]
        flex flex-col overflow-hidden
        transition-[width] duration-[var(--dur-base)]
        ${collapsed ? 'w-12' : 'w-[200px]'}
      `}
      aria-label="Navegación principal"
    >
      {/* Navegación */}
      <nav className="flex-1 p-2 flex flex-col gap-[2px]" role="navigation">
        {NAV_ITEMS.map((item) => (
          <SidebarItem key={item.key} item={item} collapsed={collapsed} />
        ))}
      </nav>

      {/* Footer con versión */}
      {!collapsed && (
        <div className="
          px-4 py-3 border-t border-[var(--border)]
          text-[11px] text-[var(--text-tertiary)] font-mono
        ">
          {t('app.version')}
        </div>
      )}
    </aside>
  )
}
