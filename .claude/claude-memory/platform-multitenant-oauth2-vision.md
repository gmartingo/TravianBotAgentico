---
name: platform-multitenant-oauth2-vision
description: "visión de evolución a plataforma multi-tenant (servicios centrales monetizables + bots en el borde) con OAuth2; SOLO discutida, sin spec aún; retomar al cerrar route-templates"
metadata: 
  node_type: memory
  type: project
  originSessionId: 144a0ba1-b756-4a96-be49-5151ef8163d2
---

Giro de arquitectura discutido el 2026-06-05 (a raíz de la herramienta de desarrollador de plantillas de rutas): evolucionar de "bot mono-usuario" a **plataforma multi-tenant**. Pendiente de construir; el usuario pidió que se lo recuerde **al terminar la feature de plantillas de rutas** ([[route-templates-developer-portal-feature]]).

**El concepto central — dos mundos separados:**
- **Plataforma central** (independiente de Travian, monetizable): catálogos compartidos que el desarrollador cura — iconos, datos kirilloid (calculadoras tropas/edificios), **plantillas de rutas maestras**, i18n. Corre una sola vez en un servidor central, se sirve vía API a todas las instancias.
- **Instancia de borde** (atada a Travian): el bot real (Chrome, perfil persistente, cuentas/mundos/sesiones, credenciales Travian). Corre en la máquina/Pi del usuario.

**Por qué el split (no es solo monetización):** la anti-detección OBLIGA a que el bot viva en el borde. Centralizar bots = misma IP/datacenter para muchas cuentas = firma trivial para Travian. El central solo sirve datos Travian-independientes.

**Decisiones ya tomadas por el usuario:**
- **Credenciales Travian SIEMPRE en el borde** (cifradas Fernet, ya está así). El central NUNCA las ve → privacidad + si comprometen el servidor no caen las cuentas.
- **OAuth2 con OIDC portable**: elegir herramienta que exista como cloud gestionado Y open-source self-hosted (**Logto** o **Zitadel**). Estrategia reversible: arrancar en su cloud gratis para llegar rápido a primeros usuarios y autohospedar después (reaprovechando el servidor central de catálogos) cuando coste/privacidad lo pidan. Objetivo: 0 € de arranque en ambas vías.

**Modelo de auth (ya pulido):**
- Dos superficies de API. La **API del borde** (login/overview/sesiones, local, mono-usuario) NO lleva auth. La **API central** (catálogos) SÍ.
- Cabecera nueva `Authorization: Bearer <JWT>` SOLO en llamadas borde→central; se suma a `Accept-Language` (ortogonales). La instancia del bot se vuelve cliente OAuth.
- Validación stateless: JWT firmado, se verifica contra JWKS del IdP (cacheado), sin llamar al IdP por request. En FastAPI = una dependencia más, idéntico patrón a `get_language`/`resolve_language`, pero en el proyecto central.
- Monetización vía códigos: **401** = no autenticado; **403** = autenticado pero el plan no incluye el scope (botón "actualiza suscripción"). Los scopes/claims del token codifican el tier.

**Tensiones pendientes de resolver en el análisis futuro:**
- Stack BD: el central multi-tenant probablemente quiere Postgres + hosting (reabre la decisión "SQLite suficiente para 1 usuario" de CLAUDE.md); el borde sigue con SQLite local.
- Coste de infra: pasar de "0 infra" a un servidor central 24/7.
- Reparto fino de qué endpoints suben al central vs se quedan en el borde, y qué tiers/scopes gatea cada uno (no llegamos a pulir esto).

**Estado:** SOLO discutido. Sin spec en docs/specs/. Al retomar: `palantir` (qué ya es "plataforma-independiente" reaprovechable: catálogos, route-templates, i18n) → `analista`.
