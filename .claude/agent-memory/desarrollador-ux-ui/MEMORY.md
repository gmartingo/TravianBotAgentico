# MEMORY.md — desarrollador-ux-ui

- [frontend-stack](frontend-stack.md) — Stack React+Vite+Tailwind v4, estructura src/, comandos dev/build
- [i18n-system](i18n-system.md) — Sistema i18n: 25 idiomas, catálogo en src/i18n/catalog/, fallback es, RTL
- [design-tokens](design-tokens.md) — Tokens CSS duales en src/styles/tokens.css, cablear con @theme inline en app.css
- [patterns-ui-components](patterns-ui-components.md) — Patrones de tabla/tarjeta/skeleton/modal/estados, dark mode con CSS vars, accesibilidad de filas
- [patterns-wizard-modal](patterns-wizard-modal.md) — Wizard modal S3: routing overlay, focus trap, parseo URL Travian, API 2 pasos
- [patterns-account-detail](patterns-account-detail.md) — S4+S5-S8: máquina de sesión por mundo, RowMenu sin overflow-hidden, modales reutilizables, uiUtils
- [patterns-world-space](patterns-world-space.md) — S9 WorldSpacePage: shell sidebar+world-header+bottom-bar, FarmListsTab, FarmListDrawer, ProbeMenu inline, huecos API conocidos
- [patterns-farm-feedback](patterns-farm-feedback.md) — S10 feedback UI: SchedulerSubPanel accordion, SchedulerDashboard drill-down, SendFeedback, StatsPanel, huecos API toggle/timestamp
- [patterns-human-sessions](patterns-human-sessions.md) — S11 Human Sessions: pestaña Sesión, tokens modo, componentes session/, validateCoverage, API client métodos nuevos
- [patterns-oasis-spawn](patterns-oasis-spawn.md) — S-SPAWN: SpawnMechanicsPanel+OasisCompositionPanel+WorstCasePlannerPanel, catálogo JS, claves NATURE_N, carga EP-SPAWN compartida
- [patterns-noise-tab](patterns-noise-tab.md) — S-NOISE: pestaña Ruido, wizard de rutas, Toggle/MinMaxInput, DeletePopover inline, EP-N01..N13
- [patterns-animal-frequency](patterns-animal-frequency.md) — AnimalFrequencyPanel: normalización array→objeto, arcilla→barro, ResIcon para botín, coordUtils, tablist ARIA con flechas
- [patterns-route-templates](patterns-route-templates.md) — RouteTemplatesPage /rutas: sin peso en plantilla, origen=desplegable, InheritedStepsPanel EP-RT11, TestRoutePanel v3 sesión+cierre
