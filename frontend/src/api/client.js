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
}
