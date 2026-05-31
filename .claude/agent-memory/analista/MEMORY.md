# Memory index

- [project-i18n-backend](project_i18n_backend.md) — Decisiones cerradas del diseño de i18n del backend (catálogo, puerto, excepciones, endpoints)
- [project-arch-conventions](project_arch_conventions.md) — Convenciones de arquitectura hexagonal y API observadas en TravianBot
- [project-kirilloid-scraper](project_kirilloid_scraper.md) — Decisiones cerradas del scraper de kirilloid para tropas: puertos, persistencia híbrida, iconos, API
- [project-overview-tronco](project_overview_tronco.md) — Tronco compartido de lectura de overview: OverviewHtmlSourcePort, LiveOverviewAdapter, FixtureAdapter, VillageMap, utils parseo
- [project-overview-blocks](project_overview_blocks.md) — Bloques overview/resources/culture-points/troops: decisiones, hallazgos del fixture, selectores clave
- [project-accounts-worlds](project_accounts_worlds.md) — Diseño registro cuentas/mundos: email-unicidad, Fernet, PlayableTribe, cascada FK, WorldRuntimePort degradación segura
- [project-login-sesion-api](project_login_sesion_api.md) — SessionRegistry, cableado LiveOverviewAdapter con set_callables, 3 endpoints session, LoginFailedError
- [project-farm-lists](project_farm_lists.md) — Entidades, puertos, scheduling, browser adapter y BD de farm lists automáticas; reglas clave de anti-detección y backoff
- [project-farm-stats](project_farm_stats.md) — 4 gaps de farm stats: last_send_time, metadata scheduler en historial, slot_bounty_history (drop total_bounty), endpoint /stats
- [project-simulador-combate](project_simulador_combate.md) — Simulador/optimizador de combate; spec en draft (pendiente revisión v4 API: drops por recurso {wood,clay,iron,crop,total}, default attack_type="raid")
- [project-oasis-farming](project_oasis_farming.md) — Oasis farming: roles en FarmScheduler, grupos, máquina 3 estados; refactorizado 2026-05-29: ciclo global extraído a human-sessions.md
- [project-human-sessions](project_human_sessions.md) — Ciclo HARDCORE/REST_SESSION en WorldAgent: factor intervalo REST, parada oasis en REST, warmup 20-30min; prerrequisito de oasis-farming.md
