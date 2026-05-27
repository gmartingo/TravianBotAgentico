# Memory index

- [guardian-agent-not-invocable](guardian-agent-not-invocable.md) — guardian-antideteccion no es invocable como subagent_type; usar general-purpose con su .md
- [autonomous-git-execution](autonomous-git-execution.md) — el usuario autoriza ejecutar git autónomamente; el push necesita auth que él debe configurar
- [deferred-game-data-layer](deferred-game-data-layer.md) — datos de juego (niveles/costes/stats) aplazados a feature futura con scraper de kirilloid; i18n solo traduce
- [kirilloid-scraper-gotchas](kirilloid-scraper-gotchas.md) — gotchas zendriver (find vs select, properties, screenshot_b64) + kirilloid SPA hash + numeración global de iconos
- [third-party-scraper-no-antidetection](third-party-scraper-no-antidetection.md) — scrapers de terceros (kirilloid) NO necesitan guardian anti-detección; solo proteger driver.py + perfil separado
- [travian-lectura-overview-endpoints](travian-lectura-overview-endpoints.md) — feature endpoints lectura Travian (overview/resources/culture/troops): live+TTL, parsers desacoplados con HTML real, 4 equipos paralelos, palantir+coordinador globales
- [permission-prompts-preference](permission-prompts-preference.md) — odia los prompts de permiso; defaultMode acceptEdits fijado, ir al lever global no incremental
- [speed-modifier-runtime-not-data](speed-modifier-runtime-not-data.md) — velocidad servidor (x1..x10) = divisor de tiempos en runtime (API/core), NO se scrapea; solo la versión T4.5/T4.6 es dimensión de datos
- [registro-cuentas-mundos-feature](registro-cuentas-mundos-feature.md) — feature cuentas/mundos implementada (email lobby + Fernet, perfil Chrome por cuenta); 653 passed, los 2 fallos CA-20 son de lectura-overview; pendiente prueba manual + commit
- [login-sesion-api-feature](login-sesion-api-feature.md) — API de sesión (login/logout/estado) implementada y validada en Travian real; SessionRegistry + descifrado Fernet; depende de live_overview_adapter
- [fernet-key-must-be-persisted](fernet-key-must-be-persisted.md) — TRAVIAN_BOT_SECRET_KEY debe ir fija en ~/.zshrc o las contraseñas guardadas quedan indescifrables (InvalidToken→401 sin abrir Chrome)
- [documentador-prefer-editing](documentador-prefer-editing.md) — el documentador debe editar/ampliar docs existentes por caso de uso, no crear ficheros nuevos por defecto
- [tailwind-v4-reset-must-be-layered](tailwind-v4-reset-must-be-layered.md) — el reset CSS global debe ir en @layer base o anula todo el espaciado de Tailwind v4 (UI "amontonada"); cómo verificar UI con captura headless de Chrome
- [ui-testing-puppeteer-core](ui-testing-puppeteer-core.md) — frontend/scripts/uishot.mjs (puppeteer-core + Chrome del sistema) para testear interacciones del front y verificar con captura ANTES de enseñar al usuario; solo localhost, nunca Travian
- [branch-hygiene-one-feature-per-branch](branch-hygiene-one-feature-per-branch.md) — una feature = una rama bien nombrada; git-flow-advisor debe avisar si el contenido no encaja con la rama activa (pasó: kirilloid-buildings acabó de cajón de sastre)
- [feedback-palantir-always-first](feedback-palantir-always-first.md) — palantir SIEMPRE primero, sin excepción, aunque la tarea llegue completamente especificada
