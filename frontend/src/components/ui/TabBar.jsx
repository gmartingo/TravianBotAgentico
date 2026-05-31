/**
 * TabBar — Strip horizontal de pestañas reutilizable.
 *
 * Diseño: underline de 2px en var(--accent) bajo el label del tab activo (no fondo).
 * Accesibilidad: role="tablist", cada tab role="tab", aria-selected, aria-controls.
 *
 * Props:
 *   tabs      — [{ id: string, label: string }]
 *   activeTab — string (id del tab activo)
 *   onTabChange — (id: string) => void
 *   panelId   — función (id) => string  para aria-controls
 */
export function TabBar({ tabs, activeTab, onTabChange, panelId }) {
  function handleKeyDown(e, currentIdx) {
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      const next = (currentIdx + 1) % tabs.length
      onTabChange(tabs[next].id)
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const prev = (currentIdx - 1 + tabs.length) % tabs.length
      onTabChange(tabs[prev].id)
    } else if (e.key === 'Home') {
      e.preventDefault()
      onTabChange(tabs[0].id)
    } else if (e.key === 'End') {
      e.preventDefault()
      onTabChange(tabs[tabs.length - 1].id)
    }
  }

  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      style={{
        display: 'flex',
        borderBottom: '1px solid var(--border)',
        gap: '0',
        overflowX: 'auto',
        scrollbarWidth: 'none',
      }}
    >
      {tabs.map((tab, idx) => {
        const isActive = tab.id === activeTab
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            aria-controls={panelId ? panelId(tab.id) : `tabpanel-${tab.id}`}
            id={`tab-${tab.id}`}
            type="button"
            tabIndex={isActive ? 0 : -1}
            onClick={() => onTabChange(tab.id)}
            onKeyDown={(e) => handleKeyDown(e, idx)}
            style={{
              position: 'relative',
              padding: '10px 16px',
              border: 'none',
              borderBottom: isActive
                ? '2px solid var(--accent)'
                : '2px solid transparent',
              marginBottom: '-1px',
              background: 'transparent',
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontSize: '14px',
              fontWeight: isActive ? 600 : 400,
              color: isActive ? 'var(--accent-text)' : 'var(--text-secondary)',
              transition: 'color var(--dur-fast), border-color var(--dur-fast)',
              whiteSpace: 'nowrap',
              outline: 'none',
            }}
            onFocus={(e) => {
              e.currentTarget.style.boxShadow = '0 0 0 2px var(--accent)'
              e.currentTarget.style.borderRadius = 'var(--radius-sm) var(--radius-sm) 0 0'
            }}
            onBlur={(e) => {
              e.currentTarget.style.boxShadow = 'none'
              e.currentTarget.style.borderRadius = '0'
            }}
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}
