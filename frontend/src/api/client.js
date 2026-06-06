/**
 * Cliente HTTP del dashboard TravianBot.
 *
 * Reglas (CLAUDE.md — "Cliente HTTP — cabecera de idioma obligatoria"):
 *   - Base URL: /api (el proxy de Vite retira /api → :8000 sin prefijo).
 *   - Envía Accept-Language: <localStorage['lang'] || 'es'> en CADA petición.
 *   - Maneja JSON + errores { detail } de FastAPI.
 *   - Un 400/4xx con {detail} lanza ApiError con ese mensaje.
 *   - Un error de red lanza ApiError con clave 'error.network'.
 *
 * Uso:
 *   import { api } from './client.js'
 *   const accounts = await api.get('/accounts')
 *   const account  = await api.post('/accounts', { email, username, password })
 */

const BASE = '/api'

// Error tipado para distinguir errores de API de otros
export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function getLang() {
  return localStorage.getItem('lang') || 'es'
}

function buildHeaders(extra = {}) {
  return {
    'Content-Type': 'application/json',
    'Accept-Language': getLang(),
    ...extra,
  }
}

/**
 * Normaliza el campo `detail` de FastAPI a un STRING legible.
 *
 * FastAPI devuelve `detail` como string en errores de negocio (400/404/409),
 * pero como ARRAY de objetos `{loc, msg, type}` en errores de validación (422).
 * Si ese array/objeto llega tal cual a la UI y se intenta renderizar como hijo
 * de React, lanza "Objects are not valid as a React child" y tumba el árbol
 * (pantalla en gris, sin botones). Aquí lo aplanamos siempre a string.
 */
function normalizeDetail(detail) {
  if (detail == null) return null
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((e) => (typeof e === 'string' ? e : e?.msg))
      .filter(Boolean)
    return msgs.length ? msgs.join(' · ') : JSON.stringify(detail)
  }
  if (typeof detail === 'object') return detail.msg ?? JSON.stringify(detail)
  return String(detail)
}

async function parseResponse(res) {
  // Intentar parsear JSON siempre; si falla, devolver texto plano
  const contentType = res.headers.get('content-type') || ''
  const isJson = contentType.includes('application/json')

  if (res.ok) {
    if (res.status === 204) return null
    return isJson ? res.json() : res.text()
  }

  // Error: intentar extraer {detail} de FastAPI
  let detail = `HTTP ${res.status}`
  if (isJson) {
    try {
      const body = await res.json()
      detail = normalizeDetail(body.detail) ?? detail
    } catch (_) {
      // ignorar errores de parseo
    }
  }

  throw new ApiError(detail, res.status, detail)
}

async function request(method, path, body, extraHeaders) {
  try {
    const opts = {
      method,
      headers: buildHeaders(extraHeaders),
    }
    if (body !== undefined) {
      opts.body = JSON.stringify(body)
    }
    const res = await fetch(`${BASE}${path}`, opts)
    return parseResponse(res)
  } catch (err) {
    if (err instanceof ApiError) throw err
    // Error de red (fetch rechazado)
    throw new ApiError('error.network', 0, 'error.network')
  }
}

// ── Funciones por endpoint ──────────────────────────────────

// Cuentas
export const api = {
  /** GET /accounts → lista de cuentas (la API responde {accounts:[...]}, devolvemos el array) */
  getAccounts: () => request('GET', '/accounts').then((d) => d?.accounts ?? []),

  /** GET /accounts/:id → detalle de cuenta */
  getAccount: (id) => request('GET', `/accounts/${id}`),

  /** POST /accounts → { email, username, password } → 201 */
  createAccount: (data) => request('POST', '/accounts', data),

  /** PUT /accounts/:id → { email, username, password? } → 200 */
  updateAccount: (id, data) => request('PUT', `/accounts/${id}`, data),

  /** DELETE /accounts/:id → 204 */
  deleteAccount: (id) => request('DELETE', `/accounts/${id}`),

  // Mundos
  /** GET /accounts/:id/worlds → lista de mundos (la API responde {worlds:[...]}, devolvemos el array) */
  getWorlds: (accountId) =>
    request('GET', `/accounts/${accountId}/worlds`).then((d) => d?.worlds ?? []),

  /** POST /accounts/:id/worlds → { server_url, tribe } → 201 */
  createWorld: (accountId, data) => request('POST', `/accounts/${accountId}/worlds`, data),

  /** DELETE /accounts/:id/worlds/:worldId → 204 */
  deleteWorld: (accountId, worldId) =>
    request('DELETE', `/accounts/${accountId}/worlds/${worldId}`),

  // Sesión (backend YA implementado: POST/DELETE/GET .../session).
  // POST es síncrono (~3-10s, login real). El frontend espera el 200 para entrar al mundo;
  // 401 = login fallido (se queda en el detalle con error).

  /** GET /accounts/:id/worlds/:worldId/session → estado de sesión */
  getSession: (accountId, worldId) =>
    request('GET', `/accounts/${accountId}/worlds/${worldId}/session`),

  /** POST /accounts/:id/worlds/:worldId/session → arrancar */
  startSession: (accountId, worldId) =>
    request('POST', `/accounts/${accountId}/worlds/${worldId}/session`),

  /** DELETE /accounts/:id/worlds/:worldId/session → parar */
  stopSession: (accountId, worldId) =>
    request('DELETE', `/accounts/${accountId}/worlds/${worldId}/session`),

  // ── Farm — Schedulers ─────────────────────────────────────────────────────

  /** GET /farm/worlds/:worldId/schedulers → lista de schedulers */
  getSchedulers: (worldId) =>
    request('GET', `/farm/worlds/${worldId}/schedulers`),

  /** POST /farm/worlds/:worldId/schedulers → 201 scheduler creado */
  createScheduler: (worldId, data) =>
    request('POST', `/farm/worlds/${worldId}/schedulers`, data),

  /** PUT /farm/worlds/:worldId/schedulers/:id → scheduler actualizado */
  updateScheduler: (worldId, schedulerId, data) =>
    request('PUT', `/farm/worlds/${worldId}/schedulers/${schedulerId}`, data),

  /** DELETE /farm/worlds/:worldId/schedulers/:id → 204 */
  deleteScheduler: (worldId, schedulerId) =>
    request('DELETE', `/farm/worlds/${worldId}/schedulers/${schedulerId}`),

  /** PUT /farm/worlds/:worldId/schedulers/:id/farm-lists → asignar listas */
  assignFarmLists: (worldId, schedulerId, farmListIds) =>
    request('PUT', `/farm/worlds/${worldId}/schedulers/${schedulerId}/farm-lists`, {
      farm_list_ids: farmListIds,
    }),

  // ── Farm — Farm Lists ─────────────────────────────────────────────────────

  /** GET /farm/worlds/:worldId/farm-lists → lista de farm lists con slots */
  getFarmLists: (worldId) =>
    request('GET', `/farm/worlds/${worldId}/farm-lists`),

  /** POST /farm/worlds/:worldId/farm-lists/read → sincronizar desde Travian */
  readFarmLists: (worldId) =>
    request('POST', `/farm/worlds/${worldId}/farm-lists/read`),

  // ── Farm — Slots ──────────────────────────────────────────────────────────

  /** POST /farm/slots/:slotId/activate */
  activateSlot: (slotId, farmListId, worldId) =>
    request('POST', `/farm/slots/${slotId}/activate`, { farm_list_id: farmListId, world_id: worldId }),

  /** POST /farm/slots/:slotId/deactivate */
  deactivateSlot: (slotId, farmListId, worldId) =>
    request('POST', `/farm/slots/${slotId}/deactivate`, { farm_list_id: farmListId, world_id: worldId }),

  /** POST /farm/slots/:slotId/cancel-probe */
  cancelProbe: (slotId, farmListId, worldId, mode) =>
    request('POST', `/farm/slots/${slotId}/cancel-probe`, {
      farm_list_id: farmListId,
      world_id: worldId,
      mode,
    }),

  // ── Farm — Envío manual ───────────────────────────────────────────────────

  /** POST /farm/farm-lists/:farmListId/send */
  sendFarmList: (farmListId, worldId) =>
    request('POST', `/farm/farm-lists/${farmListId}/send`, { world_id: worldId }),

  // ── Farm — Historial ──────────────────────────────────────────────────────

  /** GET /farm/worlds/:worldId/history?farm_list_id=...&page=...&page_size=... */
  getFarmListHistory: (worldId, farmListId, page = 1, pageSize = 20) =>
    request('GET', `/farm/worlds/${worldId}/history?farm_list_id=${farmListId}&page=${page}&page_size=${pageSize}`),

  // ── Farm — Historial global + slot-events ────────────────────────────────

  /**
   * GET /farm/worlds/:worldId/history?scheduler_id=...&from_dt=...&to_dt=...&page=...&page_size=...
   * Historial paginado de envíos de todo el mundo (sin filtro de lista).
   */
  getWorldHistory: (worldId, params = {}) => {
    const qs = new URLSearchParams()
    if (params.schedulerId) qs.set('scheduler_id', params.schedulerId)
    if (params.fromDt)      qs.set('from_dt', params.fromDt)
    if (params.toDt)        qs.set('to_dt', params.toDt)
    if (params.page)        qs.set('page', params.page)
    if (params.pageSize)    qs.set('page_size', params.pageSize)
    const q = qs.toString()
    return request('GET', `/farm/worlds/${worldId}/history${q ? '?' + q : ''}`)
  },

  /**
   * GET /farm/worlds/:worldId/slot-events?from_dt=...&to_dt=...&page=...&page_size=...
   * Eventos de slots (pérdidas, sondas, reactivaciones).
   */
  getSlotEvents: (worldId, params = {}) => {
    const qs = new URLSearchParams()
    if (params.fromDt)   qs.set('from_dt', params.fromDt)
    if (params.toDt)     qs.set('to_dt', params.toDt)
    if (params.page)     qs.set('page', params.page)
    if (params.pageSize) qs.set('page_size', params.pageSize)
    const q = qs.toString()
    return request('GET', `/farm/worlds/${worldId}/slot-events${q ? '?' + q : ''}`)
  },

  // ── Catálogo — Iconos ─────────────────────────────────────────────────────

  /**
   * GET /catalog/icons?icon_type=<type>&tribe=<tribe>
   * Devuelve IconListResponse { icons: [{ icon_id, ordinal, tribe, url, width_px, height_px }] }
   * El cliente ya envía Accept-Language en cada petición.
   */
  getCatalogIcons: ({ icon_type, tribe } = {}) => {
    const params = new URLSearchParams()
    if (icon_type) params.set('icon_type', icon_type)
    if (tribe)     params.set('tribe', tribe)
    return request('GET', `/catalog/icons?${params}`)
  },

  // ── Human Sessions ────────────────────────────────────────────────────────
  // OJO: estos endpoints son DISTINTOS de getSession/startSession/stopSession
  // que gestionan la sesión de login bajo /accounts/:id/worlds/:worldId/session.
  // Estos son /worlds/:worldId/session (Human Sessions — calendario de actividad).

  /** GET /worlds/:worldId/session → estado actual de Human Sessions */
  getWorldSession: (worldId) =>
    request('GET', `/worlds/${worldId}/session`),

  /** GET /worlds/:worldId/session/timeline → 7 días de timeline */
  getWorldTimeline: (worldId) =>
    request('GET', `/worlds/${worldId}/session/timeline`),

  /** GET /worlds/:worldId/session/timeline/:weekday → timeline de un día (0=lun..6=dom) */
  getWorldTimelineDay: (worldId, weekday) =>
    request('GET', `/worlds/${worldId}/session/timeline/${weekday}`),

  /** PUT /worlds/:worldId/session/timeline/:weekday → { blocks, jitter_minutes? } */
  putWorldTimelineDay: (worldId, weekday, body) =>
    request('PUT', `/worlds/${worldId}/session/timeline/${weekday}`, body),

  /** PUT /worlds/:worldId/session/mode → { mode } */
  putWorldMode: (worldId, mode) =>
    request('PUT', `/worlds/${worldId}/session/mode`, { mode }),

  /** DELETE /worlds/:worldId/session/override → cancela el override manual (204, idempotente) */
  deleteWorldOverride: (worldId) =>
    request('DELETE', `/worlds/${worldId}/session/override`),

  // TODO: endpoint pendiente — POST /farm/schedulers/:schedulerId/toggle (pausar/activar)
  // No existe aún en el backend. El frontend llama a updateScheduler para toggle.

  // ── Farm — Agente ─────────────────────────────────────────────────────────

  /** GET /farm/worlds/:worldId/agent/status */
  getAgentStatus: (worldId) =>
    request('GET', `/farm/worlds/${worldId}/agent/status`),

  /** POST /farm/worlds/:worldId/agent/start */
  startAgent: (worldId) =>
    request('POST', `/farm/worlds/${worldId}/agent/start`),

  /** POST /farm/worlds/:worldId/agent/stop */
  stopAgent: (worldId) =>
    request('POST', `/farm/worlds/${worldId}/agent/stop`),

  /** POST /farm/worlds/:worldId/schedulers/:schedulerId/run-now */
  runSchedulerNow: (worldId, schedulerId) =>
    request('POST', `/farm/worlds/${worldId}/schedulers/${schedulerId}/run-now`),

  // ── Reportes de ataque / oasis ────────────────────────────────────────────

  /**
   * GET /attack-reports/oasis → { total, items: [...] }
   * EP-08: Lista todos los oasis con reportes ordenados por último ataque DESC.
   * Cada item: { coord_x_dest, coord_y_dest, attack_count, last_attack, total_bounty }
   */
  listOasisSummaries: () =>
    request('GET', '/attack-reports/oasis'),

  /**
   * GET /attack-reports/stats/global
   * EP-09: Estadísticas globales de todos los oasis combinados
   * (animal_appearances + animal_regen_rates agregados de toda la BD).
   */
  getGlobalOasisStats: () =>
    request('GET', '/attack-reports/stats/global'),

  /**
   * GET /attack-reports/stats/oasis?x=<int>&y=<int>
   * EP-06: Estadísticas de un oasis (apariciones, repoblación, animal_regen_rates).
   */
  getOasisStats: (x, y) =>
    request('GET', `/attack-reports/stats/oasis?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}`),

  /**
   * GET /attack-reports/stats/balance → balance global PERDIDOS vs ROBADOS.
   * Parámetros opcionales: x, y (oasis), from_date, to_date (ISO 8601 con segundos).
   * Devuelve { range, total_reports, reports_without_tribe, lost, stolen, net }.
   */
  getBalanceStats: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.x != null)    qs.set('x', params.x)
    if (params.y != null)    qs.set('y', params.y)
    if (params.from_date)    qs.set('from_date', params.from_date)
    if (params.to_date)      qs.set('to_date', params.to_date)
    const q = qs.toString()
    return request('GET', `/attack-reports/stats/balance${q ? '?' + q : ''}`)
  },

  /**
   * GET /attack-reports → lista paginada de reportes
   * Parámetros opcionales: x, y, fromDt, toDt, page, pageSize.
   */
  getAttackReports: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.x != null)  qs.set('x', params.x)
    if (params.y != null)  qs.set('y', params.y)
    if (params.fromDt)     qs.set('from_dt', params.fromDt)
    if (params.toDt)       qs.set('to_dt', params.toDt)
    if (params.page)       qs.set('page', params.page)
    if (params.pageSize)   qs.set('page_size', params.pageSize)
    const q = qs.toString()
    return request('GET', `/attack-reports${q ? '?' + q : ''}`)
  },

  /**
   * GET /attack-reports/:id → detalle completo de un reporte.
   */
  getAttackReport: (id) =>
    request('GET', `/attack-reports/${id}`),

  /**
   * POST /attack-reports/parse → parsear texto de reporte.
   */
  parseAttackReport: (raw_text) =>
    request('POST', '/attack-reports/parse', { raw_text }),

  /**
   * POST /attack-reports → guardar reporte parseado.
   */
  saveAttackReport: (data) =>
    request('POST', '/attack-reports', data),

  /**
   * DELETE /attack-reports/:id → 204.
   */
  deleteAttackReport: (id) =>
    request('DELETE', `/attack-reports/${id}`),

  /**
   * GET /attack-reports/stats/oasis/spawn-composition?timer_min=<6|7|10|15>
   * EP-SPAWN: composición típica, peor combinación y estado cooldown/respawn por oasis.
   * timer_min obligatorio. Fuera de {6,7,10,15} → 400.
   */
  getOasisSpawnComposition: (timerMin) =>
    request('GET', `/attack-reports/stats/oasis/spawn-composition?timer_min=${timerMin}`),

  /**
   * GET /attack-reports/stats/oasis/temporal-distribution?interval_minutes=<6|7|10|15|30|60|120|180|240|300>
   * EP-TD: distribución empírica de animales por cadencia de farmeo (v4).
   * intervalMinutes: default 240 (4h). Valores válidos: {6,7,10,15,30,60,120,180,240,300}. Fuera → 400.
   * Envía Accept-Language desde localStorage (obligatorio en este endpoint).
   * buildHeaders() ya incluye Accept-Language automáticamente — no hace falta extra.
   * Schema v4: respuesta incluye types[5] (hierro/arcilla/madera/cereal/sin_clasificar).
   *   Cada sección: { oasis_type, oasis_type_label, n_oasis, n_oasis_low_confidence,
   *                   n_reports_in_section,
   *                   oasis_coords: [{x,y}]  — [v4] oasis con gap en la ventana (y ASC, x ASC),
   *                   avg_bounty: {wood,clay,iron,crop,total}  — [v4] media botín por reporte,
   *                   total_animals: {avg,mode,max,n_valid,n_total}  — [v4] total animales/reporte,
   *                   animals[]: [..., max_present: int|null]  — [v4] máximo present sobre n_valid }.
   *   El campo animals[] de la raíz de v2 desaparece — ahora vive dentro de cada sección.
   * Ver spec docs/specs/bd-ataques-oasis-temporal-distribution.md §8 EP-TD (v4).
   */
  getAnimalTemporalDistribution: (intervalMinutes = 240) => {
    const params = new URLSearchParams({ interval_minutes: intervalMinutes })
    return request('GET', `/attack-reports/stats/oasis/temporal-distribution?${params}`)
  },

  // ── Noise (Catálogo de Ruido) ─────────────────────────────────────────────
  // EP-N01..N13 — /worlds/:worldId/noise/...

  /** EP-N01 GET /worlds/:worldId/noise/config → NoiseConfig */
  getNoiseConfig: (worldId) =>
    request('GET', `/worlds/${worldId}/noise/config`),

  /** EP-N02 PUT /worlds/:worldId/noise/config → NoiseConfig actualizada */
  putNoiseConfig: (worldId, data) =>
    request('PUT', `/worlds/${worldId}/noise/config`, data),

  /** EP-N03 GET /worlds/:worldId/noise/destinations → lista de destinos */
  getNoiseDestinations: (worldId) =>
    request('GET', `/worlds/${worldId}/noise/destinations`),

  /** EP-N04 POST /worlds/:worldId/noise/destinations → 201 destino creado */
  createNoiseDestination: (worldId, data) =>
    request('POST', `/worlds/${worldId}/noise/destinations`, data),

  /** EP-N05 PUT /worlds/:worldId/noise/destinations/:destId → destino actualizado */
  updateNoiseDestination: (worldId, destId, data) =>
    request('PUT', `/worlds/${worldId}/noise/destinations/${destId}`, data),

  /** EP-N06 DELETE /worlds/:worldId/noise/destinations/:destId → 204 */
  deleteNoiseDestination: (worldId, destId) =>
    request('DELETE', `/worlds/${worldId}/noise/destinations/${destId}`),

  /** EP-N07 GET /worlds/:worldId/noise/destinations/:destId/paths → lista de rutas con pasos */
  getNoisePaths: (worldId, destId) =>
    request('GET', `/worlds/${worldId}/noise/destinations/${destId}/paths`),

  /** EP-N08 POST /worlds/:worldId/noise/destinations/:destId/paths → 201 ruta creada */
  createNoisePath: (worldId, destId, data) =>
    request('POST', `/worlds/${worldId}/noise/destinations/${destId}/paths`, data),

  /** EP-N09 PUT /worlds/:worldId/noise/paths/:pathId → ruta actualizada (is_active, steps…) */
  updateNoisePath: (worldId, pathId, data) =>
    request('PUT', `/worlds/${worldId}/noise/paths/${pathId}`, data),

  /** EP-N10 DELETE /worlds/:worldId/noise/paths/:pathId → 204 */
  deleteNoisePath: (worldId, pathId) =>
    request('DELETE', `/worlds/${worldId}/noise/paths/${pathId}`),

  /** EP-N11 POST /worlds/:worldId/noise/derive-selector → deriva selector CSS del outerHTML */
  deriveNoiseSelector: (worldId, outerHtml) =>
    request('POST', `/worlds/${worldId}/noise/derive-selector`, { outer_html: outerHtml }),

  /** EP-N12 GET /worlds/:worldId/noise/origins → anclas semilla (genéricas + por-aldea) */
  getNoiseOrigins: (worldId) =>
    request('GET', `/worlds/${worldId}/noise/origins`),

  /** EP-N13 POST /worlds/:worldId/noise/refresh-villages → refresca aldeas desde el browser */
  refreshNoiseVillages: (worldId) =>
    request('POST', `/worlds/${worldId}/noise/refresh-villages`, {}),

  /** EP-N14 POST /worlds/:worldId/noise/paths/:pathId/test → ejecuta ruta en vivo y devuelve reporte */
  testNoisePath: (worldId, pathId) =>
    request('POST', `/worlds/${worldId}/noise/paths/${pathId}/test`),

  // ── Plantillas de rutas (Portal del desarrollador /rutas) ────────────────
  // EP-RT01..EP-RT10 — /route-templates/...
  // Nota: estos endpoints no requieren Accept-Language (labels = texto libre del dev).
  // buildHeaders() ya lo incluye igualmente (inofensivo).

  /**
   * EP-RT01 GET /route-templates — lista plantillas.
   * params: { category?, include_paths?, limit?, offset? }
   */
  listRouteTemplates: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.category)      qs.set('category', params.category)
    if (params.include_paths) qs.set('include_paths', 'true')
    if (params.limit != null) qs.set('limit', params.limit)
    if (params.offset != null) qs.set('offset', params.offset)
    const q = qs.toString()
    return request('GET', `/route-templates${q ? '?' + q : ''}`)
  },

  /** EP-RT02 POST /route-templates — crear plantilla → 201 */
  createRouteTemplate: (data) =>
    request('POST', '/route-templates', data),

  /** EP-RT03 GET /route-templates/:id — obtener plantilla con paths+steps */
  getRouteTemplate: (id) =>
    request('GET', `/route-templates/${id}`),

  /** EP-RT04 PUT /route-templates/:id — PATCH parcial de plantilla */
  updateRouteTemplate: (id, data) =>
    request('PUT', `/route-templates/${id}`, data),

  /** EP-RT05 DELETE /route-templates/:id — borrar plantilla → 204 */
  deleteRouteTemplate: (id) =>
    request('DELETE', `/route-templates/${id}`),

  /** EP-RT06 GET /route-templates/:id/paths — listar paths de la plantilla */
  getRouteTemplatePaths: (id) =>
    request('GET', `/route-templates/${id}/paths`),

  /**
   * EP-RT07 POST /route-templates/:id/clone-to-world/:worldId — clonar plantilla a un mundo.
   * force: boolean (default false) — sobreescribe si hay conflicto.
   * navigation_weight: float [0.1-5.0] (default 1.0) — frecuencia con la que ESE mundo usará la ruta.
   * El peso vive en NoiseDestination por-mundo (v2 rev.2); la plantilla no tiene peso propio.
   */
  cloneRouteTemplate: (id, worldId, force = false, navigationWeight = 1.0) =>
    request(
      'POST',
      `/route-templates/${id}/clone-to-world/${worldId}${force ? '?force=true' : ''}`,
      { navigation_weight: navigationWeight },
    ),

  /**
   * EP-RT08 POST /worlds/:worldId/noise/apply-templates — bulk clone.
   * data: { template_ids: [...], force?: boolean, default_navigation_weight?: float }
   * default_navigation_weight: peso aplicado uniformemente a todos los clones del bulk (default 1.0).
   */
  applyRouteTemplatesBulk: (worldId, data) =>
    request('POST', `/worlds/${worldId}/noise/apply-templates`, data),

  /**
   * EP-RT09 POST /route-templates/:id/sync-to-world/:worldId — re-sincronizar instancia.
   */
  syncRouteTemplate: (id, worldId) =>
    request('POST', `/route-templates/${id}/sync-to-world/${worldId}`),

  /**
   * EP-RT10 POST /route-templates/:id/test — probar plantilla en vivo.
   * data: { world_id, path_index? }
   */
  testRouteTemplate: (id, data) =>
    request('POST', `/route-templates/${id}/test`, data),

  // ── Categorías de rutas ───────────────────────────────────────────────────
  // EP-CAT01..EP-CAT05 — /route-categories/
  // Nota: no requieren Accept-Language (labels = texto libre del usuario).
  // buildHeaders() ya lo incluye igualmente (inofensivo).

  /**
   * EP-CAT01 GET /route-categories → lista todas las categorías
   * Respuesta: [{ slug, label, color, is_default, created_at }]
   * Orden: is_default DESC, created_at ASC (la default siempre primera).
   */
  listCategories: () =>
    request('GET', '/route-categories'),

  /**
   * EP-CAT02 POST /route-categories → crear categoría
   * Body: { label, color? }
   * Respuesta 201: { slug, label, color, is_default, created_at }
   * 409 si label duplicado CI.
   */
  createCategory: (data) =>
    request('POST', '/route-categories', data),

  /**
   * EP-CAT03 GET /route-categories/:slug → obtener una categoría por slug
   */
  getCategory: (slug) =>
    request('GET', `/route-categories/${slug}`),

  /**
   * EP-CAT04 PATCH /route-categories/:slug → actualizar label y/o color
   * Body: { label?, color? } — al menos uno de los dos.
   * color ausente → conservar; color: null → quitar color.
   * 409 si nuevo label duplicado CI; 404 si slug no existe.
   */
  patchCategory: (slug, data) =>
    request('PATCH', `/route-categories/${slug}`, data),

  /**
   * EP-CAT05 DELETE /route-categories/:slug → borrar categoría
   * Reasigna atómicamente sus plantillas/destinos a 'uncategorized'.
   * Respuesta 200: { deleted_slug, reassigned_count, reassigned_to }
   * 409 si es la categoría default.
   */
  deleteCategory: (slug) =>
    request('DELETE', `/route-categories/${slug}`),

  /**
   * EP-RT11 GET /route-templates/:id/chain — resolver cadena de orígenes.
   * Devuelve la secuencia ordenada de pasos [raíz → hoja] que el motor ejecutaría.
   * Usado por la tabla de "pasos heredados" en el portal de rutas.
   */
  getRouteTemplateChain: (id) =>
    request('GET', `/route-templates/${id}/chain`),

  /**
   * EP-RT12 DELETE /worlds/:worldId/session — cerrar sesión Chrome de un mundo.
   * Cierra la sesión activa del mundo (browser + session_registry) sin hacer logout de Travian.
   * Usado por TestRoutePanel (v3) para liberar el browser tras el test.
   */
  closeWorldSession: (worldId) =>
    request('DELETE', `/worlds/${worldId}/session`),

  // ── Combate ───────────────────────────────────────────────────────────────
  // Restaurado desde feature/optimizador-balance-multiraid (calculadora de combate).

  combat: {
    /**
     * POST /combat/simulate
     * Body: { attacker: AttackerInput, defenders: DefenderInput[] }
     * Response: CombatSimulationResponse
     */
    simulate: (body) =>
      request('POST', '/combat/simulate', body),

    /**
     * POST /combat/optimize
     * Body: { attacker: AttackerInput, defenders: DefenderInput[], ... }
     * Response: CombatOptimizeResponse
     */
    optimize: (body) =>
      request('POST', '/combat/optimize', body),
  },
}
