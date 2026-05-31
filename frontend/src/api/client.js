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
      detail = body.detail ?? detail
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

  // ── Reportes de ataques a oasis ─────────────────────────────────────────────

  /**
   * POST /attack-reports/parse
   * Body: { raw_text }
   * Response: { attacked_at, utc_offset, coord_x_dest, coord_y_dest,
   *             origin_village_name, attacker_troops[], animals[], bounty{...},
   *             hero_inventory (null | {wood,clay,iron,crop}),
   *             already_exists, existing_id }
   * Throws ApiError (status 422 con detail legible si parse falla)
   */
  parseAttackReport: (raw_text) =>
    request('POST', '/attack-reports/parse', { raw_text }),

  /**
   * POST /attack-reports
   * Body: { raw_text }
   * Response: 201 { id, attacked_at, utc_offset, coord_x_dest, coord_y_dest, origin_village_name }
   * Throws ApiError (status 409 si duplicado)
   */
  saveAttackReport: (raw_text) =>
    request('POST', '/attack-reports', { raw_text }),

  /**
   * GET /attack-reports?x=&y=&from_date=&to_date=&limit=&offset=
   * Response: { items: [...], total, cumulative_bounty }
   */
  getAttackReports: (queryString = '') =>
    request('GET', `/attack-reports${queryString ? '?' + queryString : ''}`),

  /**
   * GET /attack-reports/{id}
   * Response: detalle completo (misma shape que parse)
   */
  getAttackReport: (id) =>
    request('GET', `/attack-reports/${id}`),

  /**
   * DELETE /attack-reports/{id} → 204
   */
  deleteAttackReport: (id) =>
    request('DELETE', `/attack-reports/${id}`),

  /**
   * GET /attack-reports/stats/oasis?x=&y=
   * Response: { coord_x_dest, coord_y_dest, total_attacks, first_attack, last_attack,
   *             animal_appearances[], repopulation_gaps[] }
   * Si sin datos → total_attacks 0 y listas vacías
   */
  getOasisStats: (x, y) =>
    request('GET', `/attack-reports/stats/oasis?x=${x}&y=${y}`),

  // ── Combate ───────────────────────────────────────────────────────────────

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
