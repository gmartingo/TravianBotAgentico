---
name: registro-cuentas-mundos-feature
description: "Estado de la feature de registro/persistencia de cuentas y mundos (implementada, pendiente prueba manual + commit)"
metadata: 
  node_type: memory
  type: project
  originSessionId: e82e3551-50d4-4464-85df-1652fc4e450f
---

Feature **registro-cuentas-mundos** (spec en docs/specs/registro-cuentas-mundos.md, estado: implemented). Implementada el 2026-05-25 pero **pendiente del gate humano** (prueba manual del usuario) y por tanto **sin commitear**.

Modelo: cuenta identificada por **email de lobby** (un email/password → varios mundos), cada mundo con su tribu jugable. Contraseñas cifradas con **Fernet**; requiere env var `TRAVIAN_BOT_SECRET_KEY` o la app no arranca (RN-04). Perfil de Chrome **por cuenta** (`profiles/account_{id}/`). 8 endpoints REST /accounts y /accounts/{id}/worlds, sin Accept-Language (datos operativos). Aldeas fuera de alcance (tabla creada, sin API).

Suite: **653 passed, 2 failed**. Los 2 fallos (`tests/antideteccion/test_ca20_catalogo_no_en_browser.py`) son de la feature **lectura-overview** (parsers en adapters/browser/parsers/ con nombres de catálogo y translation_port hardcodeados) — NO de esta feature; los debe resolver guardian-antideteccion cuando se trabaje [[travian-lectura-overview-endpoints]].

Deuda técnica documentada (palantir, no bloqueante): D-3 `_now_iso` duplicado entre adaptadores SQLite; D-4 warning runtime_port repetido en use cases; F-4 router accede a `db._conn` (falta exponer created_at/updated_at vía port o entidad).

**Login-sesión backend (2026-05-26):** feature login-sesion-api (spec docs/specs/login-sesion-api.md) IMPLEMENTADA + guardian-antideteccion APTO PARA COMMIT. 3 endpoints POST/DELETE/GET /accounts/{id}/worlds/{world_id}/session (login síncrono ~3-10s, logout idempotente, estado). SessionRegistry (adapters/browser/session_registry.py) implementa WorldRuntimePort in-memory y delega 100% en adapters/browser/login.py (intacto). 71 tests verdes (57 feature + 14 anti-detección en tests/antideteccion/test_session_antideteccion.py). PENDIENTE: prueba manual del usuario (login real en Travian vía Swagger) + commit. Aviso preexistente fuera de alcance: login.py loguea username/server a nivel WARNING (posible tarea aparte). UI: affordance arrancar/parar en design spec + mockup, pero frontend React aún NO existe.

**Frontend React (2026-05-26):** implementado en frontend/ (Vite+Tailwind v4). Pantallas: lista de cuentas (acciones Editar/Borrar en el ⋯), wizard de alta 2 pasos (/cuentas/nueva), detalle de cuenta limpio (solo breadcrumb+mundos) con arrancar/parar/entrar por mundo (login real vía API de sesión), espacio del mundo (/mundos/:id, vacío con "← Mundos", sin diseñar dentro aún). i18n COMPLETO: 25 idiomas × 163 claves en src/i18n/catalog/ (es/en cuidados, 23 [AUTO] máquina pendientes de revisión nativa), RTL para ar/he/fa verificado. Gotcha resuelto: [[tailwind-v4-reset-must-be-layered]]. Verificación UI propia con [[ui-testing-puppeteer-core]]. Dev server expuesto en LAN con host:true (móvil); inputs de modales a text-[16px] md:text-[14px] para evitar auto-zoom iOS.

**RELEASE v0.1.0 en main (2026-05-26):** merge develop→main 1642a2f (--no-ff) + tag anotado v0.1.0, pusheado a GitHub. main contiene: cuentas/mundos, login-sesión, lectura overview, kirilloid (edificios+tropas), dashboard React 25 idiomas, 741 tests verdes, docs + manual usuario ES/EN (documentacion/manual-usuario/{es,en}/index.html, landing con selector). Gate de release: NO borrar travian_bot.db (tiene la cuenta del usuario; los tests usan BD temporal propia).

**COMMITEADO Y PUSHEADO (2026-05-26):** rama feature/kirilloid-buildings en origin. login-sesión backend = be2e449 (sesión previa); frontend = 2b2ea13 (feat(frontend), 42 ficheros); docs = 324b869. registro-cuentas-mundos CRUD = c0458dc. Follow-ups NO bloqueantes: CS-01 (dedup WizardModal vs uiUtils, palantir lo registró), drawer móvil, lazy-load i18n por idioma, revisión nativa de los 23 idiomas [AUTO], contenido del WorldSpacePage (Etapa 2 sin diseñar), enmascarar username/server en log de login.py, manual de usuario HTML. La feature lectura-overview sigue a medias y con CA-20 en rojo (anti-detección) — NO commiteada, otra línea de trabajo.

**UI/UX (2026-05-25):** diseño en docs/design/gestion-cuentas-mundos.md (ready-for-impl) + 3 mockups en frontend/mockups/ (cuentas / wizard / cuenta-detalle .playground.html). Decisiones: solo gestión CRUD (sin login al dashboard, sin botón activar bot — WorldRuntimePort no existe), shell con sidebar macOS, páginas separadas (/cuentas, /cuentas/:id), alta wizard 2 pasos, password tras enlace "Cambiar contraseña", URL pegada + mostrada parseada, select 7 tribus hardcodeadas, desktop-first. Flujo mockup-first DESIGN.md §18: PENDIENTE aprobación visual del usuario → luego palantir cierre (reutilización) → luego desarrollador-ux-ui implementa (scaffold React+Vite+Tailwind no existe aún).

**Why:** el flujo del proyecto exige prueba manual del usuario antes de commit; ningún agente puede saltarlo.
**How to apply:** para probar, generar y exportar `TRAVIAN_BOT_SECRET_KEY` (estable, si cambia no se descifran contraseñas viejas), arrancar la API y probar en Swagger /docs.
