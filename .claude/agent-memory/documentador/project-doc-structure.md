---
name: project-doc-structure
description: Estructura y convenciones de documentación del proyecto TravianBot — dónde vive cada tipo de doc
metadata:
  type: project
---

La documentación técnica del proyecto vive en `documentacion/` (raíz del proyecto). El índice maestro es `documentacion/README.md`.

**Organización de carpetas**:
- `documentacion/backend/` — documentación funcional de código (tipo 1)
- `documentacion/backend/referencia-funciones/` — referencia rápida de funciones/métodos
- `documentacion/api/` — referencia de endpoints REST
- `documentacion/funcionalidades/` — documentación de negocio (tipo 2) por feature
- `documentacion/procesos/` — guías de proceso del equipo

**Por qué existe en `documentacion/` y no en `docs/`**: `docs/` contiene specs funcionales (`docs/specs/`) y specs de diseño (`docs/design/`). Son los inputs. `documentacion/` contiene la documentación derivada del código real (outputs del documentador).

**Convención de marca de agua**: cada documento lleva al pie `🔖 Última revisión: YYYY-MM-DD`. Al actualizar, bumpear la fecha a la actual.

**Regla de oro**: actualizar, nunca duplicar. Antes de crear, leer `documentacion/README.md` para ver si ya existe un documento relacionado.

**Why**: el CLAUDE.md del proyecto define esta estructura. Antes de la sesión de 2026-05-24 solo existía `documentacion/procesos/operativa-por-fases.md`. El README maestro y todas las carpetas de documentación se crearon en la sesión de documentación de i18n-backend.

**Features documentadas (2026-05-26)**:
- `i18n-backend` → `backend/i18n.md`, `funcionalidades/i18n-backend.md`, `api/catalogo.md`
- `sesion` (login/logout/estado) → `backend/sesion.md` (ya existía completo), `funcionalidades/sesion.md`, `api/sesion.md`, `backend/referencia-funciones/sesion.md`
- `cuentas-mundos` (CRUD + sesión extremo a extremo + frontend) → `api/cuentas-mundos.md` (creado), `funcionalidades/cuentas-mundos.md` (creado), `frontend/dashboard.md` (creado en nueva carpeta `documentacion/frontend/`)

**Carpeta nueva añadida**: `documentacion/frontend/` para documentar el dashboard React. Registrada en `documentacion/README.md`.

**Patrón observado**: para features con backend complejo, los docs de backend (`backend/sesion.md`, `api/sesion.md`, `funcionalidades/sesion.md`) pueden ser creados directamente por el desarrollador/agente antes de que el documentador intervenga. Siempre verificar qué existe antes de crear.

**Divergencias conocidas detectadas en sesión 2026-05-26**:
- `docs/design/gestion-cuentas-mundos.md §4b` indica "backend de sesión no existe aún" — en realidad está completamente implementado. Documentado en `funcionalidades/cuentas-mundos.md`.
- El diseño S1 muestra Recursos/Tropas/Construcción como ítems disabled en el sidebar de Gestión. El código `Sidebar.jsx` solo tiene "Cuentas". Divergencia aceptada, documentada en `frontend/dashboard.md`.

**How to apply**: al documentar cualquier feature nueva, seguir esta estructura. Enlazar siempre desde `documentacion/README.md`.
