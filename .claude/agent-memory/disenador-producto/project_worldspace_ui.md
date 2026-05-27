---
name: project-worldspace-ui
description: Estructura de WorldSpacePage y convenciones de diseño establecidas para las pestañas internas del mundo
metadata:
  type: project
---

WorldSpacePage es una pantalla full-screen sin sidebar de gestión (ruta separada del ManagementShell).
Tiene su propia topbar mínima con "← Mundos" + controles tema/idioma. Las secciones se implementan
como pestañas internas con el patrón `world-tabs` (border-bottom activo en var(--accent)).

Pestañas previstas (2026-05-26):
- Dashboard — resumen de actividad del bot en ese mundo
- Schedulers — control del farmeo automático (DISEÑADO: docs/design/farm-lists-ui.md)
- Listas de vacas — gestión de farm lists (DISEÑADO: docs/design/farm-lists-ui.md)
- Calculadora de ejércitos — pendiente de diseño

El mockup base del mundo vive en frontend/mockups/mundo.playground.html y ya incluye la topbar,
el world-header con tabs, y el patrón de contenido de pestaña. Los nuevos playgrounds deben
seguir exactamente los mismos tokens y estructura visual.

**Why:** El mundo es el espacio de trabajo principal del bot — cada mundo que el usuario gestiona
tiene su propio conjunto de schedulers, listas, aldeas y sesión de browser.

**How to apply:** Cualquier feature nueva de WorldSpacePage debe diseñarse como una pestaña más
siguiendo el patrón establecido. El spec funcional de farm-lists.md es la fuente de verdad para
la lógica de negocio de schedulers y farm lists.
