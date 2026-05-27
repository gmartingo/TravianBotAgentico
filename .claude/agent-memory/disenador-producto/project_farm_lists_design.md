---
name: project-farm-lists-design
description: Decisiones de diseño clave de la UI de Farm Lists (Schedulers + Listas de vacas + Dashboard + Feedback)
metadata:
  type: project
---

Spec base: docs/design/farm-lists-ui.md (estado: implemented).
Mockup base aprobado: frontend/mockups/farm-lists.playground.html.

Spec delta (feedback/dashboard): docs/design/farm-lists-feedback.md (estado: ready-for-impl).
Mockup delta: frontend/mockups/farm-lists-feedback.playground.html (PENDIENTE de crear).

Nuevas superficies añadidas en el spec delta (2026-05-27):
- Pestaña Dashboard en WorldSpacePage: KPIs del día (envíos, slots activos, desactivadas) +
  feed de actividad reciente con polling ~10s + fila nueva resaltada --accent-subtle 2-3s +
  panel Alertas separado con contador de no-leídas (estado local de sesión).
- Panel feedback post-envío en FarmListDrawer: debajo del botón "Enviar ahora", muestra
  status badge + N slots raideando + vacas desactivadas del último envío. Se reemplaza en
  el siguiente envío. No se muestra si nunca se ha enviado.
- Pestaña Stats en FarmListDrawer (tercera pestaña, tras Slots e Historial): botín total,
  media por envío, envíos 7 días, barras de distribución de estados, top slots. Calculado
  localmente desde los datos ya cargados (sin endpoint extra).

Decisiones clave:
- Schedulers = lista de cards; cada card tiene: nombre, toggle enabled, chips de listas asignadas,
  countdown HH:MM:SS al próximo envío. El countdown usa --font-mono tabular-nums.
- Panel de agente encima de la lista de cards, ocupa ancho completo. Muestra estado
  running/stopped/error/paused con icono + color + texto. Cuando parado: countdowns muestran "—".
- Intervalos en el form de scheduler se expresan en MINUTOS (el frontend convierte a ms para la API).
  Mínimo 1 min (anti-detección, RN-02 del spec funcional).
- Listas de vacas agrupadas por aldea propietaria (village_name + coordenadas).
- Columna Slots = activos/total (en danger si 0 activos).
- Drawer (slideout desde end) para el detalle de una farm list. Ancho 480px desktop, 100% mobile.
  Drawer tiene pestañas internas: Slots | Historial.
- Slots: tabla densa con accordion por fila (expandir = ver cooldown countdown + acciones).
  "Cancelar sonda" tiene confirmación INLINE (no modal extra) con dos opciones: deactivate/send_now.
- Historial: tabla paginada, paginación "Cargar más" explícita.
- Sincronización automática en primer uso (no botón forzado). El botón es fallback visible si falla.

Componentes nuevos requeridos: AgentStatusPanel, SchedulerCard, SchedulerFormModal,
AssignFarmListsModal, FarmListsTab, FarmListDrawer, SlotRow, SlotDetail,
SendHistoryTable, SlotStatusBadge, Countdown, IntervalInput.

Componentes reutilizados: ConfirmDeleteModal, useFocusTrap, Spinner, showToast,
patrón loading/empty/error de AccountsListPage, máquina de estados de AccountDetailPage.

**Why:** El usuario tiene dos modos de uso bien distintos: monitorización rápida (P1: countdown
y estado del agente) y configuración (P2/P3: crear schedulers, asignar listas, gestionar slots).
El diseño de disclosure progresiva refleja esta diferencia.
