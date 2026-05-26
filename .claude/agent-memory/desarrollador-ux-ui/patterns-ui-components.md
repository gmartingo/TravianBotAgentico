---
name: patterns-ui-components
description: Patrones y convenciones de componentes React del proyecto — tablas, tarjetas, menús, skeletons, modales, estados vacío/error/cargando
metadata:
  type: project
---

Patrones consolidados en la implementación de S2 (AccountsListPage):

**Estilos inline con CSS vars**: NO usar `dark:` de Tailwind para modo oscuro. Los tokens ya cambian con `data-theme="dark"` via CSS. Usar siempre `var(--token)` en className o style. El `dark:` de Tailwind v4 por defecto usa media query, no `data-theme`.

**Fondos semánticos con opacidad sobre tokens**: Para banners de estado (error, aviso) usar `color-mix(in srgb, var(--danger) 10%, transparent)` en style. Evita hardcodear RGBA que no responden al tema.

**Skeleton pulse**: Clase global `skeleton-pulse` ya definida en `app.css` (`@keyframes skeleton-pulse`). Aplicar a elementos con `bg-[var(--surface-2)]`.

**Tabla responsive**: `hidden md:block` para tabla desktop, `md:hidden` para tarjetas móvil. Columnas P3 con `hidden lg:table-cell`.

**Menú contextual (⋯)**: Componente local con `useRef` + `useEffect` para cerrar al click fuera y con Escape. Posicionado `absolute end-0` (lógico, funciona en RTL).

**Modal de confirmación**: `role="dialog" aria-modal="true"`, foco automático al botón de confirmación via `useRef + useEffect`, Escape cierra.

**Cuatro estados de página**: `status: 'loading' | 'data' | 'empty' | 'error'`. El banner de error se muestra ENCIMA de la cabecera (sección de página visible en estado error también muestra la tabla vacía con cabecera).

**Respaldo de campo API**: La API de cuentas devuelve `worlds_count` (no `worlds`). Fallback `?? 0` para campos opcionales.

**Formato de fecha**: `Intl.DateTimeFormat(lang, { day: 'numeric', month: 'short', year: 'numeric' })` con el `lang` del contexto i18n.

**Caption plural**: Usa `t('page.accounts.caption', { n })` — el sistema i18n resuelve `.pl` automáticamente cuando `n !== 1`.

**Navegación**: `useNavigate` de react-router-dom, ruta a detalle `/cuentas/:id`, ruta wizard `/cuentas/nueva`.

**Accesibilidad filas tabla**: `tabIndex={0}` + `onKeyDown` para Enter/Space en filas clicables. Guardia `e.target.closest('button')` para no activar navegación al pulsar el menú.

**Why**: Reglas extraídas al implementar S2 Lista de cuentas siguiendo mockup aprobado en `frontend/mockups/cuentas.playground.html`.

**How to apply**: Reutilizar estos patrones en S3 (wizard), S4 (detalle), etc. No reinventar: buscar aquí primero.
