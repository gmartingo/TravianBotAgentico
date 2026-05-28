/**
 * FarmListDrawer — V5/V6/V6-delta Drawer lateral de detalle de farm list.
 *
 * Desliza desde el extremo `end` (inset-inline-end: 0).
 * 480px en desktop (≥ lg), 100vw en mobile.
 *
 * Pestañas internas:
 *  - Slots (V5/V6/V6-delta): 3 stat chips + tabla de slots con accordion (V6)
 *    V6-delta: sort por columna, iconos de tropas, dropdown ⋯, botín acum., link reporte
 *  - Stats (V9): distribución + top slots
 *  - Historial (V5-hist): tabla de envíos + "Cargar más"
 *
 * Accesibilidad:
 *  - focus trap (useFocusTrap)
 *  - ESC cierra
 *  - aria-live="off" en countdowns
 *  - foco vuelve al triggerRef al cerrar
 *  - role="dialog" + aria-modal
 *
 * Props:
 *  - open          {boolean}
 *  - farmList      {object|null}   farm list seleccionada
 *  - worldId       {number}
 *  - schedulerName {string|null}   nombre del scheduler asignado
 *  - worldServer   {string|null}   URL base del mundo (ej. "https://ts1.travian.es/")
 *  - tribe         {string|null}   tribu del mundo (ej. "romans")
 *  - onClose       {Function}
 *  - triggerRef    {React.Ref}     ref al botón que abrió el drawer
 */
import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api, ApiError } from '../../api/client.js'
import { Spinner, useFocusTrap, showToast } from '../ui/uiUtils.jsx'
import { Countdown } from './Countdown.jsx'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtNum(n) {
  if (n == null || n === 0) return '—'
  return new Intl.NumberFormat('es').format(Math.round(n))
}

// rs (Serbian kirilloid code) → sr (BCP-47 for Intl)
const INTL_LANG_MAP = { rs: 'sr' }

function relativeTime(isoString, lang) {
  if (!isoString) return '—'
  const ms = Date.now() - new Date(isoString).getTime()
  if (isNaN(ms)) return '—'
  const diff = Math.floor(ms / 1000)
  const locale = INTL_LANG_MAP[lang] ?? lang ?? 'es'
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  if (diff < 60)    return rtf.format(-diff, 'second')
  if (diff < 3600)  return rtf.format(-Math.floor(diff / 60), 'minute')
  if (diff < 86400) return rtf.format(-Math.floor(diff / 3600), 'hour')
  return rtf.format(-Math.floor(diff / 86400), 'day')
}

function fmtTime(isoString) {
  if (!isoString) return '—'
  const d = new Date(isoString)
  if (isNaN(d.getTime())) return '—'
  return (
    String(d.getHours()).padStart(2, '0') + ':' +
    String(d.getMinutes()).padStart(2, '0') + ':' +
    String(d.getSeconds()).padStart(2, '0')
  )
}

/** Construye el ISO target para el countdown de cooldown a partir de cooldown_seconds */
function cooldownTargetIso(slot) {
  if (!slot.cooldown_seconds || slot.cooldown_seconds <= 0) return null
  const base = slot.last_raid_time ? new Date(slot.last_raid_time) : new Date()
  if (isNaN(base.getTime())) return null
  return new Date(base.getTime() + slot.cooldown_seconds * 1000).toISOString()
}

/** Construye la URL del reporte de la última raid */
function buildReportUrl(worldServer, reportId) {
  if (!worldServer || !reportId) return null
  const base = worldServer.endsWith('/') ? worldServer : worldServer + '/'
  return `${base}report?id=${reportId.replace('/', '%7C')}&s=1`
}

// ── Iconos SVG ────────────────────────────────────────────────────────────────

function IconSend({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  )
}

function IconClose({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

/** Espadas cruzadas de resultado de raid */
function IconSwords({ size = 14, color }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke={color} strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="14.5 17.5 3 6 3 3 6 3 17.5 14.5" />
      <line x1="13" y1="19" x2="19" y2="13" />
      <line x1="16" y1="16" x2="20" y2="20" />
      <line x1="19" y1="21" x2="21" y2="19" />
      <polyline points="14.5 6.5 18 3 21 3 21 6 17.5 9.5" />
      <line x1="5" y1="14" x2="8.5" y2="17.5" />
      <line x1="3" y1="19" x2="5" y2="21" />
      <line x1="4" y1="22" x2="6" y2="22" />
    </svg>
  )
}

function raidStateColor(state) {
  if (!state) return null
  if (state.includes('withoutLosses')) return 'var(--success)'       // verde
  if (state.includes('withLosses'))    return '#D4900A'              // amarillo
  if (state.includes('lost'))          return 'var(--danger)'        // rojo
  return null
}

/** Icono de enlace externo (↗) para el link de reporte */
function IconExternalLink({ size = 11 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  )
}

// ── SlotStatusBadge ───────────────────────────────────────────────────────────

function SlotStatusBadge({ slot }) {
  const { t } = useI18n()

  if (!slot.is_active && !slot.disabled_by_bot) {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: '4px',
        borderRadius: 'var(--radius-full)', padding: '1px 7px',
        fontSize: '11px', fontWeight: 500,
        background: 'var(--surface-2)', color: 'var(--text-secondary)',
      }}>
        {t('slot.status.disabledManual')}
      </span>
    )
  }

  if (slot.disabled_by_bot && slot.cooldown_seconds > 0) {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: '4px',
        borderRadius: 'var(--radius-full)', padding: '1px 7px',
        fontSize: '11px', fontWeight: 500,
        background: 'var(--accent-subtle)', color: 'var(--accent-text)',
      }}>
        {t('slot.status.probe')}
      </span>
    )
  }

  if (slot.disabled_by_bot) {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: '4px',
        borderRadius: 'var(--radius-full)', padding: '1px 7px',
        fontSize: '11px', fontWeight: 500,
        background: 'rgba(201,53,44,.10)', color: 'var(--danger)',
      }}>
        {t('slot.status.disabledBot')}
      </span>
    )
  }

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      borderRadius: 'var(--radius-full)', padding: '1px 7px',
      fontSize: '11px', fontWeight: 500,
      background: 'rgba(36,138,61,.12)', color: 'var(--success)',
    }}>
      {t('slot.status.active')}
    </span>
  )
}

// ── ProbeMenu (popover inline) ────────────────────────────────────────────────

function ProbeMenu({ open, onSelect, onClose }) {
  const { t } = useI18n()
  const menuRef = useRef(null)

  // Cerrar al hacer clic fuera
  useEffect(() => {
    if (!open) return
    function handler(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      ref={menuRef}
      role="menu"
      style={{
        position: 'absolute',
        bottom: 'calc(100% + 6px)',
        insetInlineStart: 0,
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-lg)',
        zIndex: 500,
        minWidth: '230px',
        overflow: 'hidden',
      }}
    >
      <button
        role="menuitem"
        type="button"
        onClick={() => { onSelect('deactivate'); onClose() }}
        style={{
          width: '100%',
          display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
          padding: '10px 14px',
          border: 'none', borderBottom: '1px solid var(--border)',
          background: 'transparent',
          cursor: 'pointer', fontFamily: 'inherit',
          fontSize: '13px', color: 'var(--text)', textAlign: 'start',
          gap: '2px',
          transition: 'background var(--dur-fast) var(--ease)',
        }}
        className="hover:bg-[var(--surface-2)]"
      >
        <span>{t('slot.cancelProbe.deactivate')}</span>
        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 400 }}>
          {t('slot.cancelProbe.deactivate.desc')}
        </span>
      </button>
      <button
        role="menuitem"
        type="button"
        onClick={() => { onSelect('send_now'); onClose() }}
        style={{
          width: '100%',
          display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
          padding: '10px 14px',
          border: 'none',
          background: 'transparent',
          cursor: 'pointer', fontFamily: 'inherit',
          fontSize: '13px', color: 'var(--danger)', textAlign: 'start',
          gap: '2px',
          transition: 'background var(--dur-fast) var(--ease)',
        }}
        className="hover:bg-[var(--surface-2)]"
      >
        <span>{t('slot.cancelProbe.sendNow')}</span>
        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 400 }}>
          {t('slot.cancelProbe.sendNow.desc')}
        </span>
      </button>
    </div>
  )
}

// ── SlotActions (dropdown ⋯ en la fila) ──────────────────────────────────────

function SlotActions({ slot, farmListId, worldId, onUpdated }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const menuRef = useRef(null)
  const btnRef = useRef(null)

  const hasProbe = slot.disabled_by_bot && slot.cooldown_seconds > 0

  // Cierre al hacer clic fuera (mismo patrón que ProbeMenu)
  useEffect(() => {
    if (!open) return
    function handler(e) {
      if (
        menuRef.current && !menuRef.current.contains(e.target) &&
        btnRef.current && !btnRef.current.contains(e.target)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  async function runAction(fn) {
    setLoading(true)
    setOpen(false)
    try {
      await fn()
      onUpdated()
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('slot.error.actionFailed'))
    } finally {
      setLoading(false)
    }
  }

  const handleActivate = () => runAction(() =>
    api.activateSlot(slot.id, farmListId, worldId)
  )
  const handleDeactivate = () => runAction(() =>
    api.deactivateSlot(slot.id, farmListId, worldId)
  )
  const handleProbe = (mode) => runAction(() =>
    api.cancelProbe(slot.id, farmListId, worldId, mode)
  )

  // Estilos de item de menú
  const itemStyle = (isDisabled, danger = false) => ({
    width: '100%',
    display: 'flex', alignItems: 'center', gap: '8px',
    padding: '9px 14px',
    border: 'none',
    background: 'transparent',
    cursor: isDisabled ? 'not-allowed' : 'pointer',
    fontFamily: 'inherit',
    fontSize: '13px',
    color: danger ? 'var(--danger)' : 'var(--text)',
    textAlign: 'start',
    opacity: isDisabled ? 0.6 : 1,
    transition: 'background var(--dur-fast) var(--ease)',
  })

  const subItemStyle = (isDisabled) => ({
    ...itemStyle(isDisabled),
    paddingLeft: '26px',
    fontSize: '12px',
    color: 'var(--text-secondary)',
  })

  const dividerStyle = {
    height: '1px',
    background: 'var(--border)',
    margin: '2px 0',
  }

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        ref={btnRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('slot.actions.menuLabel')}
        onClick={e => { e.stopPropagation(); setOpen(v => !v) }}
        style={{
          width: '28px', height: '28px',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          background: 'transparent',
          cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '14px', color: 'var(--text-secondary)',
          fontFamily: 'var(--font-mono)',
          transition: 'background var(--dur-fast) var(--ease)',
          flexShrink: 0,
        }}
        className="hover:bg-[var(--surface-2)]"
      >
        {loading ? <Spinner size={11} /> : '···'}
      </button>

      {open && (
        <div
          ref={menuRef}
          role="menu"
          style={{
            position: 'absolute',
            insetInlineEnd: 0,
            top: 'calc(100% + 4px)',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-lg)',
            zIndex: 600,
            minWidth: '200px',
            overflow: 'hidden',
          }}
        >
          {/* Activar (si no está activo) */}
          {!slot.is_active && (
            <button
              role="menuitem"
              type="button"
              disabled={loading}
              onClick={handleActivate}
              style={itemStyle(loading)}
              className="hover:bg-[var(--surface-2)]"
            >
              {t('slot.actions.activate')}
            </button>
          )}

          {/* Desactivar (si está activo y no desactivado por bot) */}
          {slot.is_active && !slot.disabled_by_bot && (
            <button
              role="menuitem"
              type="button"
              disabled={loading}
              onClick={handleDeactivate}
              style={itemStyle(loading)}
              className="hover:bg-[var(--surface-2)]"
            >
              {t('slot.actions.deactivate')}
            </button>
          )}

          {/* Cancelar sonda (si hay sonda) */}
          {hasProbe && (
            <>
              <div style={dividerStyle} aria-hidden="true" />
              {/* Cabecera no interactiva */}
              <div style={{
                padding: '7px 14px 4px',
                fontSize: '11px',
                color: 'var(--text-tertiary)',
                fontWeight: 500,
                textTransform: 'uppercase',
                letterSpacing: '.04em',
              }}>
                {t('slot.actions.cancelProbeHeader')}
              </div>
              <button
                role="menuitem"
                type="button"
                disabled={loading}
                onClick={() => handleProbe('deactivate')}
                style={subItemStyle(loading)}
                className="hover:bg-[var(--surface-2)]"
              >
                {t('slot.actions.probeDeactivate')}
              </button>
              <button
                role="menuitem"
                type="button"
                disabled={loading}
                onClick={() => handleProbe('send_now')}
                style={{ ...subItemStyle(loading), color: loading ? undefined : 'var(--danger)' }}
                className="hover:bg-[var(--surface-2)]"
              >
                {t('slot.actions.probeSendNow')}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── SortableHeader (componente interno de SlotsPanel) ────────────────────────

function SortableHeader({ label, colKey, sortKey, sortDir, onSort, style = {}, className }) {
  const isActive = sortKey === colKey
  return (
    <th
      scope="col"
      onClick={() => onSort(colKey)}
      aria-sort={isActive ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      className={className}
      style={{
        fontSize: '11px', color: 'var(--text-secondary)',
        textTransform: 'uppercase', letterSpacing: '.04em',
        fontWeight: 500, padding: '6px 8px',
        borderBottom: '1px solid var(--border)',
        textAlign: 'start',
        cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {label}
      {isActive
        ? <span style={{ color: 'var(--accent-text)', marginInlineStart: '3px' }}>{sortDir === 'asc' ? '▲' : '▼'}</span>
        : <span style={{ color: 'var(--text-tertiary)', fontSize: '10px', marginInlineStart: '3px' }}>⇅</span>
      }
    </th>
  )
}

// ── SlotDetail (V6, accordion expandido) ─────────────────────────────────────

function SlotDetail({ slot, farmListId, worldId, onUpdated }) {
  const { t, lang } = useI18n()
  const [probeMenuOpen, setProbeMenuOpen] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const hasProbe = slot.disabled_by_bot && slot.cooldown_seconds > 0
  const cooldownIso = cooldownTargetIso(slot)

  async function handleActivate() {
    setActionLoading(true)
    try {
      await api.activateSlot(slot.id, farmListId, worldId)
      onUpdated()
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('slot.error.actionFailed'))
    } finally {
      setActionLoading(false)
    }
  }

  async function handleDeactivate() {
    setActionLoading(true)
    try {
      await api.deactivateSlot(slot.id, farmListId, worldId)
      onUpdated()
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('slot.error.actionFailed'))
    } finally {
      setActionLoading(false)
    }
  }

  async function handleProbeAction(mode) {
    setActionLoading(true)
    try {
      await api.cancelProbe(slot.id, farmListId, worldId, mode)
      onUpdated()
    } catch (e) {
      showToast(e instanceof ApiError ? e.detail : t('slot.error.actionFailed'))
    } finally {
      setActionLoading(false)
    }
  }

  const lossText = slot.last_raid_state === 'losses'
    ? t('slot.lastRaid.withLosses')
    : t('slot.lastRaid.noLosses')

  return (
    <div style={{
      background: 'var(--surface-2)',
      borderRadius: 'var(--radius-sm)',
      padding: '12px 14px',
      marginTop: '4px',
    }}>
      {/* Cooldown countdown si hay sonda */}
      {hasProbe && cooldownIso && (
        <div style={{ marginBottom: '8px', display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <Countdown
            targetIso={cooldownIso}
            style={{
              fontSize: '17px', fontWeight: 600,
              fontFamily: 'var(--font-mono)',
              fontVariantNumeric: 'tabular-nums',
              color: 'var(--accent-text)',
            }}
          />
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            {t('slot.cooldownRemaining')}
          </span>
        </div>
      )}

      {/* Último informe */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '6px', fontSize: '13px' }}>
        <span style={{ color: 'var(--text-secondary)', minWidth: '110px' }}>
          {t('slot.lastRaid')}
        </span>
        <span>
          {slot.last_raid_state
            ? `${lossText} · ${relativeTime(slot.last_raid_time, lang)}`
            : '—'
          }
        </span>
      </div>

      {/* Botín promedio */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '6px', fontSize: '13px' }}>
        <span style={{ color: 'var(--text-secondary)', minWidth: '110px' }}>
          {t('slot.avgBounty')}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
          {fmtNum(slot.average_raid_bounty)}
        </span>
      </div>

      {/* Botín total */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '6px', fontSize: '13px' }}>
        <span style={{ color: 'var(--text-secondary)', minWidth: '110px' }}>
          {t('slot.totalBounty')}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
          {fmtNum(slot.total_bounty)}
        </span>
      </div>

      {/* Acciones */}
      <div style={{
        display: 'flex', gap: '8px', marginTop: '10px',
        flexWrap: 'wrap', position: 'relative',
      }}>
        {/* Cancelar sonda (solo si hay sonda) */}
        {hasProbe && (
          <div style={{ position: 'relative', display: 'inline-block' }}>
            <button
              type="button"
              aria-haspopup="menu"
              aria-expanded={probeMenuOpen}
              disabled={actionLoading}
              onClick={() => setProbeMenuOpen(v => !v)}
              style={{
                display: 'flex', alignItems: 'center', gap: '4px',
                height: '30px', padding: '0 10px',
                border: '1px solid var(--border-strong)',
                background: 'var(--surface)', color: 'var(--text)',
                borderRadius: 'var(--radius-sm)',
                cursor: actionLoading ? 'not-allowed' : 'pointer',
                fontSize: '12px', fontFamily: 'inherit',
                opacity: actionLoading ? 0.6 : 1,
                transition: 'background var(--dur-fast) var(--ease)',
              }}
              className="hover:bg-[var(--surface-2)]"
            >
              {t('slot.cancelProbe')}
            </button>
            <ProbeMenu
              open={probeMenuOpen}
              onSelect={handleProbeAction}
              onClose={() => setProbeMenuOpen(false)}
            />
          </div>
        )}

        {/* Activar / Desactivar */}
        {slot.is_active ? (
          <button
            type="button"
            disabled={actionLoading}
            onClick={handleDeactivate}
            style={{
              display: 'flex', alignItems: 'center', gap: '4px',
              height: '30px', padding: '0 10px',
              border: '1px solid var(--border-strong)',
              background: 'var(--surface)', color: 'var(--text)',
              borderRadius: 'var(--radius-sm)',
              cursor: actionLoading ? 'not-allowed' : 'pointer',
              fontSize: '12px', fontFamily: 'inherit',
              opacity: actionLoading ? 0.6 : 1,
              transition: 'background var(--dur-fast) var(--ease)',
            }}
            className="hover:bg-[var(--surface-2)]"
          >
            {actionLoading ? <Spinner size={11} /> : null}
            {t('slot.deactivate')}
          </button>
        ) : (
          <button
            type="button"
            disabled={actionLoading}
            onClick={handleActivate}
            style={{
              display: 'flex', alignItems: 'center', gap: '4px',
              height: '30px', padding: '0 10px',
              border: '1px solid var(--border-strong)',
              background: 'var(--surface)', color: 'var(--text)',
              borderRadius: 'var(--radius-sm)',
              cursor: actionLoading ? 'not-allowed' : 'pointer',
              fontSize: '12px', fontFamily: 'inherit',
              opacity: actionLoading ? 0.6 : 1,
              transition: 'background var(--dur-fast) var(--ease)',
            }}
            className="hover:bg-[var(--surface-2)]"
          >
            {actionLoading ? <Spinner size={11} /> : null}
            {t('slot.activate')}
          </button>
        )}
      </div>
    </div>
  )
}

// ── SlotRow (fila de slot con accordion) — V6-delta ───────────────────────────

function SlotRow({ slot, isExpanded, onToggle, farmListId, worldId, onUpdated, iconsByOrdinal, worldServer }) {
  const { t } = useI18n()

  // Construir lista de tropas ordenada por ordinal ascendente
  const troopEntries = slot.troops
    ? Object.entries(slot.troops)
        .map(([key, qty]) => ({ ordinal: parseInt(key.replace('t', ''), 10), qty }))
        .filter(e => e.qty > 0)
        .sort((a, b) => a.ordinal - b.ordinal)
    : []

  // URL del reporte de la última raid
  const reportUrl = buildReportUrl(worldServer, slot.last_raid_report_id)

  // Detener propagación del clic en la celda de acciones para no expandir el accordion
  function stopProp(e) { e.stopPropagation() }

  const tdBase = {
    borderBottom: isExpanded ? 'none' : '1px solid var(--border)',
    verticalAlign: 'middle',
  }

  return (
    <>
      <tr
        className="slot-row"
        role="button"
        tabIndex={0}
        aria-expanded={isExpanded}
        onClick={onToggle}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onToggle()}
        style={{ cursor: 'pointer' }}
      >
        {/* Columna 1: Tropas (iconos) */}
        <td style={{ ...tdBase, padding: '6px 4px 6px 8px' }}>
          <div style={{ display: 'flex', flexDirection: 'row', gap: '6px', alignItems: 'center', flexWrap: 'nowrap' }}>
            {troopEntries.map(({ ordinal, qty }) => {
              const url = iconsByOrdinal[ordinal]
              return (
                <div key={ordinal} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1px' }}>
                  {url ? (
                    <img
                      src={url}
                      alt=""
                      width={20}
                      height={20}
                      style={{ width: '20px', height: '20px', objectFit: 'contain', display: 'block' }}
                    />
                  ) : (
                    <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', lineHeight: 1 }}>
                      T{ordinal}
                    </span>
                  )}
                  <span style={{ fontSize: '10px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', lineHeight: 1 }}>
                    {qty}
                  </span>
                </div>
              )
            })}
          </div>
        </td>

        {/* Columna 2: Nombre */}
        <td style={{ ...tdBase, padding: '8px 8px', fontSize: '13px' }}>
          {slot.target_name}
        </td>

        {/* Columna 3: Dist (oculta en mobile) */}
        <td className="slot-col-dist" style={{ ...tdBase, padding: '8px 8px' }}>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '12px',
            color: 'var(--text-secondary)',
          }}>
            {slot.distance != null ? Number(slot.distance).toFixed(1) : '—'}
          </span>
        </td>

        {/* Columna 4: Botín acum (oculta en mobile) */}
        <td className="slot-col-totalBounty" style={{ ...tdBase, padding: '8px 8px', textAlign: 'end' }}>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '12px',
            fontVariantNumeric: 'tabular-nums',
            color: 'var(--text-secondary)',
          }}>
            {fmtNum(slot.total_bounty)}
          </span>
        </td>

        {/* Columna 5: Botín último + icono resultado + link reporte */}
        <td style={{ ...tdBase, padding: '8px 8px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              {raidStateColor(slot.last_raid_state) && (
                <IconSwords size={13} color={raidStateColor(slot.last_raid_state)} />
              )}
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '13px',
                fontVariantNumeric: 'tabular-nums',
              }}>
                {fmtNum(slot.last_raid_bounty)}
              </span>
            </div>
            {slot.last_raid_report_id ? (
              reportUrl ? (
                <a
                  href={reportUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={stopProp}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: '3px',
                    color: 'var(--accent-text)', fontSize: '11px',
                    textDecoration: 'none',
                    lineHeight: 1,
                  }}
                  className="hover:[text-decoration:underline]"
                >
                  <IconExternalLink size={11} />
                  {t('slot.viewReport')}
                </a>
              ) : (
                // worldServer no disponible: mostrar ID truncado
                <span style={{
                  fontSize: '11px', color: 'var(--text-tertiary)',
                  fontFamily: 'var(--font-mono)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  maxWidth: '70px',
                }}>
                  {String(slot.last_raid_report_id).slice(0, 12)}
                  {slot.last_raid_report_id.length > 12 ? '…' : ''}
                </span>
              )
            ) : (
              <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>—</span>
            )}
          </div>
        </td>

        {/* Columna 6: Estado */}
        <td style={{ ...tdBase, padding: '8px 8px' }}>
          <SlotStatusBadge slot={slot} />
        </td>

        {/* Columna 7: ⋯ acciones — click no propaga al accordion */}
        <td
          style={{ ...tdBase, padding: '4px', width: '36px', textAlign: 'center' }}
          onClick={stopProp}
          onKeyDown={stopProp}
        >
          <SlotActions
            slot={slot}
            farmListId={farmListId}
            worldId={worldId}
            onUpdated={onUpdated}
          />
        </td>
      </tr>

      {/* Fila expandida (accordion) — colSpan 7 para cubrir todas las columnas */}
      {isExpanded && (
        <tr>
          <td
            colSpan={7}
            style={{
              padding: '0 0 8px 0',
              borderBottom: '1px solid var(--border)',
            }}
          >
            <SlotDetail
              slot={slot}
              farmListId={farmListId}
              worldId={worldId}
              onUpdated={onUpdated}
            />
          </td>
        </tr>
      )}
    </>
  )
}

// ── SlotsPanel (pestaña Slots del drawer) — V6-delta ─────────────────────────

function SlotsPanel({ farmList, worldId, slots, loading, onRefresh, worldServer, tribe }) {
  const { t } = useI18n()
  const [expandedSlotId, setExpandedSlotId] = useState(null)

  // ── Sort ──────────────────────────────────────────────────────────────────
  const [sortKey, setSortKey] = useState(null)   // null | 'name' | 'distance' | 'total_bounty' | 'last_raid_bounty' | 'last_raid_state'
  const [sortDir, setSortDir] = useState('asc')

  function handleSort(colKey) {
    if (sortKey !== colKey) {
      setSortKey(colKey)
      setSortDir('asc')
    } else if (sortDir === 'asc') {
      setSortDir('desc')
    } else {
      // desc → reset
      setSortKey(null)
      setSortDir('asc')
    }
  }

  const sortedSlots = useMemo(() => {
    if (!sortKey) return slots
    return [...slots].sort((a, b) => {
      let va = a[sortKey] ?? ''
      let vb = b[sortKey] ?? ''
      if (typeof va === 'string') va = va.toLowerCase()
      if (typeof vb === 'string') vb = vb.toLowerCase()
      if (va < vb) return sortDir === 'asc' ? -1 : 1
      if (va > vb) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [slots, sortKey, sortDir])

  // ── Iconos de tropas ──────────────────────────────────────────────────────
  const [iconsByOrdinal, setIconsByOrdinal] = useState({}) // { ordinal: url }

  useEffect(() => {
    if (!tribe) return
    api.getCatalogIcons({ icon_type: 'troop', tribe })
      .then(data => {
        const map = {}
        for (const icon of data?.icons ?? []) {
          if (icon.ordinal != null) {
            // Prepender /api para usar el proxy de Vite (o nginx en prod)
            const url = icon.url.startsWith('http') ? icon.url : `/api${icon.url}`
            map[icon.ordinal] = url
          }
        }
        setIconsByOrdinal(map)
      })
      .catch(() => {}) // silencioso — fallback a texto "TN"
  }, [tribe])

  // ── Helpers ───────────────────────────────────────────────────────────────

  function toggleSlot(id) {
    setExpandedSlotId(prev => prev === id ? null : id)
  }

  const activeSlots = slots.filter(s => s.is_active).length
  const totalSlots = slots.length
  const recPerSend = farmList?.avg_bounty_per_send ?? null
  const totalAccum = farmList?.total_bounty ?? null

  // Estilos de cabecera no sortable (Tropas y ⋯)
  const thPlain = {
    fontSize: '11px', color: 'var(--text-secondary)',
    textTransform: 'uppercase', letterSpacing: '.04em',
    fontWeight: 500, padding: '6px 8px',
    borderBottom: '1px solid var(--border)',
    textAlign: 'start',
  }

  return (
    <>
      {/* 3 stat chips */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '14px' }}>
        {[
          {
            val: loading ? '…' : `${activeSlots}/${totalSlots}`,
            label: t('drawer.stat.slotsActive'),
          },
          {
            val: loading ? '…' : fmtNum(recPerSend),
            label: t('drawer.stat.recPerSend'),
          },
          {
            val: loading ? '…' : fmtNum(totalAccum),
            label: t('drawer.stat.totalAccum'),
          },
        ].map(stat => (
          <div key={stat.label} style={{
            flex: 1,
            background: 'var(--surface-2)',
            borderRadius: 'var(--radius-sm)',
            padding: '7px 10px',
          }}>
            <span style={{
              display: 'block',
              fontFamily: 'var(--font-mono)',
              fontSize: '15px', fontWeight: 600,
              letterSpacing: '-.3px',
              color: 'var(--text)',
              fontVariantNumeric: 'tabular-nums',
            }}>
              {stat.val}
            </span>
            <span style={{
              display: 'block',
              fontSize: '10px', color: 'var(--text-tertiary)',
              textTransform: 'uppercase', letterSpacing: '.04em',
              marginTop: '2px',
            }}>
              {stat.label}
            </span>
          </div>
        ))}
      </div>

      {/* Estilos responsive — ocultar columnas P3 en mobile (< 480px) */}
      <style>{`
        @media (max-width: 479px) {
          .slot-col-dist, .slot-col-totalBounty { display: none; }
        }
      `}</style>

      {/* Tabla de slots */}
      {loading ? (
        <SkeletonSlots />
      ) : slots.length === 0 ? (
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', textAlign: 'center', padding: '24px 0' }}>
          {t('drawer.slots.empty')}
        </p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {/* Tropas — no sortable, aria-label para a11y */}
              <th scope="col" aria-label={t('slot.col.troops')} style={thPlain} />

              {/* Nombre — sortable */}
              <SortableHeader
                label={t('slot.col.name')}
                colKey="target_name"
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={handleSort}
              />

              {/* Dist — sortable, oculta en mobile */}
              <SortableHeader
                label={t('slot.col.dist')}
                colKey="distance"
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={handleSort}
                className="slot-col-dist"
              />

              {/* Botín acum — sortable, oculta en mobile */}
              <SortableHeader
                label={t('slot.col.totalBounty')}
                colKey="total_bounty"
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={handleSort}
                style={{ textAlign: 'end' }}
                className="slot-col-totalBounty"
              />

              {/* Botín último — sortable */}
              <SortableHeader
                label={t('slot.col.bounty')}
                colKey="last_raid_bounty"
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={handleSort}
              />

              {/* Estado — sortable */}
              <SortableHeader
                label={t('slot.col.status')}
                colKey="last_raid_state"
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={handleSort}
              />

              {/* Acciones — no sortable, aria-label para a11y */}
              <th scope="col" aria-label={t('slot.col.actions')} style={{ ...thPlain, width: '36px' }} />
            </tr>
          </thead>
          <tbody>
            {sortedSlots.map(slot => (
              <SlotRow
                key={slot.id}
                slot={slot}
                isExpanded={expandedSlotId === slot.id}
                onToggle={() => toggleSlot(slot.id)}
                farmListId={farmList?.id}
                worldId={worldId}
                iconsByOrdinal={iconsByOrdinal}
                worldServer={worldServer}
                onUpdated={() => {
                  setExpandedSlotId(null)
                  onRefresh()
                }}
              />
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

// ── Skeleton slots ────────────────────────────────────────────────────────────

function SkeletonSlots() {
  const pulse = {
    background: 'var(--surface-2)',
    borderRadius: 'var(--radius-sm)',
    animation: 'skeleton-pulse 1.4s ease-in-out infinite',
  }
  return (
    <>
      <style>{`
        @keyframes skeleton-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.45; }
        }
      `}</style>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <tbody>
          {[1, 2, 3, 4].map(i => (
            <tr key={i}>
              {[30, 120, 40, 50, 50, 70, 28].map((w, j) => (
                <td key={j} style={{ padding: '10px 8px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ ...pulse, height: '12px', width: `${w}px` }} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

// ── HistoryPanel (pestaña Historial del drawer) ───────────────────────────────

function HistoryPanel({ farmList, worldId }) {
  const { t } = useI18n()
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const PAGE_SIZE = 20

  useEffect(() => {
    if (!farmList) return
    setLoading(true)
    setPage(1)
    api.getFarmListHistory(worldId, farmList.id, 1, PAGE_SIZE)
      .then(data => {
        const items = data?.events ?? data?.items ?? data ?? []
        setHistory(items)
        setHasMore(items.length === PAGE_SIZE)
      })
      .catch(() => showToast(t('error.loadFailed')))
      .finally(() => setLoading(false))
  }, [farmList?.id, worldId])

  async function loadMore() {
    const nextPage = page + 1
    setLoadingMore(true)
    try {
      const data = await api.getFarmListHistory(worldId, farmList.id, nextPage, PAGE_SIZE)
      const items = data?.events ?? data?.items ?? data ?? []
      setHistory(prev => [...prev, ...items])
      setHasMore(items.length === PAGE_SIZE)
      setPage(nextPage)
    } catch {
      showToast(t('error.loadFailed'))
    } finally {
      setLoadingMore(false)
    }
  }

  function statusBadge(status) {
    const map = {
      success: { bg: 'rgba(36,138,61,.12)', color: 'var(--success)', text: t('history.status.success') },
      partial:  { bg: 'var(--accent-subtle)', color: 'var(--accent-text)', text: t('history.status.partial') },
      error:    { bg: 'rgba(201,53,44,.10)', color: 'var(--danger)', text: t('history.status.error') },
    }
    const s = map[status] ?? { bg: 'var(--surface-2)', color: 'var(--text-secondary)', text: t('history.status.unknown') }
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: '4px',
        borderRadius: 'var(--radius-full)', padding: '1px 6px',
        fontSize: '11px', fontWeight: 500,
        background: s.bg, color: s.color,
      }}>
        {s.text}
      </span>
    )
  }

  if (loading) return <SkeletonSlots />

  if (history.length === 0) {
    return (
      <p style={{
        fontSize: '13px', color: 'var(--text-secondary)',
        textAlign: 'center', padding: '24px 0',
      }}>
        {t('history.empty')}
      </p>
    )
  }

  return (
    <>
      <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
        {t('history.last7days')}
      </p>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {[t('history.col.time'), t('history.col.status'), t('history.col.slots'), t('history.col.origin')].map(h => (
              <th key={h} scope="col" style={{
                fontSize: '11px', color: 'var(--text-secondary)',
                textTransform: 'uppercase', letterSpacing: '.04em',
                fontWeight: 500, padding: '6px 8px',
                borderBottom: '1px solid var(--border)',
                textAlign: 'start',
              }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {history.map((ev, i) => (
            <tr key={ev.id ?? i}>
              <td style={{
                padding: '8px 8px', borderBottom: '1px solid var(--border)',
                fontFamily: 'var(--font-mono)', fontSize: '12px',
                fontVariantNumeric: 'tabular-nums',
              }}>
                {fmtTime(ev.sent_at ?? ev.created_at)}
              </td>
              <td style={{ padding: '8px 8px', borderBottom: '1px solid var(--border)' }}>
                {statusBadge(ev.status)}
              </td>
              <td style={{
                padding: '8px 8px', borderBottom: '1px solid var(--border)',
                fontFamily: 'var(--font-mono)', fontSize: '12px',
                fontVariantNumeric: 'tabular-nums',
              }}>
                {ev.slots_sent ?? '—'}/{ev.slots_total ?? '—'}
              </td>
              <td style={{
                padding: '8px 8px', borderBottom: '1px solid var(--border)',
                fontSize: '11px', color: 'var(--text-secondary)',
              }}>
                {ev.triggered_by === 'scheduler'
                  ? t('history.triggered.scheduler')
                  : t('history.triggered.manual')
                }
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasMore && (
        <div style={{ textAlign: 'center', paddingTop: '12px' }}>
          <button
            type="button"
            onClick={loadMore}
            disabled={loadingMore}
            style={{
              border: '1px solid var(--border-strong)',
              background: 'var(--surface)',
              color: 'var(--text-secondary)',
              height: '30px', padding: '0 14px',
              borderRadius: 'var(--radius-sm)',
              fontFamily: 'inherit', fontSize: '12px',
              cursor: loadingMore ? 'not-allowed' : 'pointer',
              opacity: loadingMore ? 0.6 : 1,
            }}
          >
            {loadingMore ? <Spinner size={11} /> : t('history.loadMore')}
          </button>
        </div>
      )}
    </>
  )
}

// ── SendFeedback — panel de resultado post-envío (v5/v6) ─────────────────────
// Muestra el resultado del último "Enviar ahora" con fade-in.

function SendFeedback({ result, t }) {
  // result: { status, slots_sent, slots_total, deactivated_slots, error_msg } | null
  if (!result) return null

  const statusMap = {
    success: { bg: 'rgba(36,138,61,.10)', color: 'var(--success)', icon: '✓', label: t('feedback.status.success') },
    partial:  { bg: 'var(--accent-subtle)',  color: 'var(--accent-text)',  icon: '⚠', label: t('feedback.status.partial') },
    error:    { bg: 'rgba(201,53,44,.08)',  color: 'var(--danger)',       icon: '✗', label: t('feedback.status.error') },
  }
  const s = statusMap[result.status] ?? { bg: 'var(--surface-2)', color: 'var(--text-secondary)', icon: '?', label: t('feedback.status.unknown') }

  const deactivated = result.deactivated_slots ?? []
  const showMore = deactivated.length > 2

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        background: s.bg,
        border: `1px solid ${s.color}30`,
        borderRadius: 'var(--radius-sm)',
        padding: '10px 14px',
        marginBottom: '8px',
        animation: 'feedback-fadein 0.25s ease',
      }}
    >
      <style>{`
        @keyframes feedback-fadein {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: deactivated.length ? '6px' : 0 }}>
        <span aria-hidden="true" style={{ color: s.color, fontWeight: 600, fontSize: '13px' }}>{s.icon}</span>
        <span style={{ fontSize: '13px', fontWeight: 500, color: s.color }}>{s.label}</span>
        {result.slots_sent != null && (
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)', marginInlineStart: 'auto' }}>
            {t('feedback.slotsRaiding').replace('{n}', result.slots_sent)}
          </span>
        )}
      </div>
      {deactivated.length === 0 ? (
        <p style={{ fontSize: '11px', color: 'var(--text-tertiary)', margin: 0 }}>
          {t('feedback.noDeactivated')}
        </p>
      ) : (
        <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
          <span>{t('feedback.deactivatedLabel')} </span>
          {deactivated.slice(0, 2).map((n, i) => (
            <span key={i}>
              <span style={{ fontWeight: 500 }}>{n}</span>
              {i < Math.min(deactivated.length, 2) - 1 ? ', ' : ''}
            </span>
          ))}
          {showMore && (
            <span style={{ color: 'var(--text-tertiary)' }}>
              {' '}{t('feedback.deactivatedMore').replace('{n}', deactivated.length - 2)}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// ── StatsPanel — pestaña Stats del drawer (v7) ────────────────────────────────

function StatsPanel({ farmList, slots }) {
  const { t } = useI18n()

  // Métricas calculadas desde los datos de slots disponibles
  const totalBounty = farmList?.total_bounty ?? 0
  const avgPerSend  = farmList?.avg_bounty_per_send ?? 0

  const activeSlots        = slots.filter(s => s.is_active).length
  const probeSlots         = slots.filter(s => s.disabled_by_bot && s.cooldown_seconds > 0).length
  const botDisabledSlots   = slots.filter(s => s.disabled_by_bot && !(s.cooldown_seconds > 0)).length
  const manualDisabledSlots = slots.filter(s => !s.is_active && !s.disabled_by_bot).length

  const topSlots = [...slots]
    .filter(s => s.average_raid_bounty > 0)
    .sort((a, b) => (b.average_raid_bounty ?? 0) - (a.average_raid_bounty ?? 0))
    .slice(0, 5)

  const hasData = totalBounty > 0 || avgPerSend > 0 || slots.some(s => s.average_raid_bounty > 0)

  if (!hasData) {
    return (
      <div style={{ textAlign: 'center', padding: '32px 16px' }}>
        <p style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
          {t('stats.empty.title')}
        </p>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
          {t('stats.empty.subtitle')}
        </p>
      </div>
    )
  }

  const StatRow = ({ label, value }) => (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '8px 0', borderBottom: '1px solid var(--border)',
    }}>
      <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{
        fontSize: '14px', fontWeight: 600,
        fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
        color: 'var(--text)',
      }}>{value}</span>
    </div>
  )

  const distData = [
    { label: t('stats.dist.active'),         count: activeSlots,         color: 'var(--success)' },
    { label: t('stats.dist.probe'),          count: probeSlots,          color: 'var(--accent-text)' },
    { label: t('stats.dist.botDisabled'),    count: botDisabledSlots,    color: 'var(--danger)' },
    { label: t('stats.dist.manualDisabled'), count: manualDisabledSlots, color: 'var(--text-tertiary)' },
  ].filter(d => d.count > 0)

  const totalSlots = slots.length || 1 // evitar /0

  return (
    <div>
      {/* Rendimiento general */}
      <p style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase',
        letterSpacing: '.06em', color: 'var(--text-tertiary)', marginBottom: '8px' }}>
        {t('stats.section.performance')}
      </p>
      <div style={{ marginBottom: '20px' }}>
        <StatRow label={t('stats.totalBounty')} value={`${fmtNum(totalBounty)} ${t('stats.bountyUnit')}`} />
        <StatRow label={t('stats.avgPerSend')}  value={`${fmtNum(avgPerSend)} ${t('stats.bountyUnit')}`} />
      </div>

      {/* Distribución de slots */}
      <p style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase',
        letterSpacing: '.06em', color: 'var(--text-tertiary)', marginBottom: '8px' }}>
        {t('stats.section.distribution')}
      </p>
      <div style={{ marginBottom: '20px' }}>
        {/* Barra visual de distribución */}
        <div style={{
          display: 'flex', borderRadius: 'var(--radius-sm)',
          overflow: 'hidden', height: '8px', marginBottom: '10px',
          background: 'var(--surface-2)',
        }} aria-hidden="true">
          {distData.map(d => (
            <div key={d.label} style={{
              background: d.color,
              width: `${(d.count / totalSlots) * 100}%`,
              transition: 'width var(--dur-slow)',
            }} />
          ))}
        </div>
        {/* Leyenda */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 16px' }}>
          {distData.map(d => (
            <div key={d.label} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span style={{
                width: '8px', height: '8px',
                borderRadius: '50%', background: d.color, flexShrink: 0,
              }} aria-hidden="true" />
              <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                {d.label}: <strong style={{ color: 'var(--text)' }}>{d.count}</strong>
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Top slots por botín */}
      {topSlots.length > 0 && (
        <>
          <p style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase',
            letterSpacing: '.06em', color: 'var(--text-tertiary)', marginBottom: '8px' }}>
            {t('stats.section.topSlots')}
          </p>
          <div>
            {topSlots.map((slot, idx) => (
              <div key={slot.id} style={{
                display: 'flex', alignItems: 'center', gap: '10px',
                padding: '7px 0', borderBottom: '1px solid var(--border)',
              }}>
                <span style={{
                  width: '20px', flexShrink: 0,
                  fontSize: '11px', color: 'var(--text-tertiary)',
                  fontFamily: 'var(--font-mono)', textAlign: 'end',
                }}>
                  {idx + 1}.
                </span>
                <span style={{ flex: 1, fontSize: '13px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {slot.target_name}
                </span>
                {slot.distance != null && (
                  <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', flexShrink: 0 }}>
                    {t('stats.topSlots.distance').replace('{d}', Number(slot.distance).toFixed(1))}
                  </span>
                )}
                <span style={{
                  fontSize: '12px', fontWeight: 600,
                  fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
                  color: 'var(--accent-text)', flexShrink: 0,
                }}>
                  {t('stats.topSlots.avgBounty').replace('{n}', fmtNum(slot.average_raid_bounty))}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── FarmListDrawer (exportación principal) ────────────────────────────────────

export function FarmListDrawer({
  open,
  farmList,
  worldId,
  schedulerName,
  worldServer,
  tribe,
  onClose,
  triggerRef,
}) {
  const { t } = useI18n()
  const [activeTab, setActiveTab] = useState('slots')
  const [slots, setSlots] = useState([])
  const [loadingSlots, setLoadingSlots] = useState(false)
  const [sending, setSending] = useState(false)
  // Resultado del último "Enviar ahora" (panel feedback v5/v6)
  const [lastSendResult, setLastSendResult] = useState(null)

  const drawerRef = useRef(null)
  useFocusTrap(drawerRef, open)

  // Cargar slots cuando se abre o cambia el farmList
  const loadSlots = useCallback(() => {
    if (!farmList || !worldId) return
    setLoadingSlots(true)
    api.getFarmLists(worldId)
      .then(data => {
        const raw = Array.isArray(data) ? data : (data?.farm_lists ?? [])
        const current = raw.find(fl => fl.id === farmList.id)
        const newSlots = current?.slots ?? farmList.slots ?? []
        setSlots(Array.isArray(newSlots) ? newSlots : [])
      })
      .catch(() => showToast(t('error.loadFailed')))
      .finally(() => setLoadingSlots(false))
  }, [farmList?.id, worldId])

  useEffect(() => {
    if (open && farmList) {
      setActiveTab('slots')
      setLastSendResult(null)
      setSlots(Array.isArray(farmList.slots) ? farmList.slots : [])
      loadSlots()
    } else if (!open) {
      setSlots([])
      setLoadingSlots(false)
    }
  }, [open, farmList?.id])

  // ESC cierra el drawer
  useEffect(() => {
    if (!open) return
    function handleKey(e) {
      if (e.key === 'Escape') {
        onClose()
        triggerRef?.current?.focus()
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose, triggerRef])

  async function handleSendNow() {
    if (!farmList) return
    setSending(true)
    setLastSendResult(null)
    try {
      const result = await api.sendFarmList(farmList.id, worldId)
      // La API puede devolver el resultado de envío o null (204). Normalizamos.
      const normalized = result ?? { status: 'success' }
      setLastSendResult(normalized)
    } catch (e) {
      setLastSendResult({ status: 'error', error_msg: e instanceof ApiError ? e.detail : t('farmLists.error.sendFailed') })
    } finally {
      setSending(false)
    }
  }

  function handleBackdropClick(e) {
    if (e.target === e.currentTarget) {
      onClose()
      triggerRef?.current?.focus()
    }
  }

  const subtitle = [
    farmList?.village_name
      ? `${farmList.village_name} (${farmList.village_x},${farmList.village_y})`
      : null,
    schedulerName,
  ].filter(Boolean).join(' · ')

  // Pestañas del drawer (Slots, Stats, Historial)
  const drawerTabs = [
    { id: 'slots',   label: t('drawer.slots.title') },
    { id: 'stats',   label: t('stats.title') },
    { id: 'history', label: t('drawer.history.title') },
  ]

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={handleBackdropClick}
        aria-hidden="true"
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,.4)',
          zIndex: 300,
          opacity: open ? 1 : 0,
          pointerEvents: open ? 'auto' : 'none',
          transition: 'opacity var(--dur-slow) var(--ease)',
        }}
      />

      {/* Panel del drawer */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label={farmList?.name ?? t('drawer.slots.title')}
        style={{
          position: 'fixed',
          top: 0, bottom: 0,
          insetInlineEnd: 0,
          width: 'min(640px, 100vw)',
          background: 'var(--bg)',
          display: 'flex', flexDirection: 'column',
          boxShadow: 'var(--shadow-lg)',
          overflow: 'hidden',
          zIndex: 310,
          transform: open ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform var(--dur-slow) var(--ease)',
          // En RTL el drawer viene de la izquierda
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '12px',
          padding: '16px 20px',
          borderBottom: '1px solid var(--border)',
          background: 'var(--surface)',
          flexShrink: 0,
        }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: '17px', fontWeight: 600, letterSpacing: '-.01em',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {farmList?.name ?? ''}
            </div>
            {subtitle && (
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                {subtitle}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => { onClose(); triggerRef?.current?.focus() }}
            aria-label={t('modal.edit.closeBtn')}
            style={{
              appearance: 'none', border: 'none', background: 'transparent',
              color: 'var(--text-secondary)',
              width: '32px', height: '32px',
              borderRadius: 'var(--radius-sm)',
              display: 'grid', placeItems: 'center',
              fontSize: '18px', cursor: 'pointer',
              flexShrink: 0,
            }}
            className="hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
          >
            <IconClose />
          </button>
        </div>

        {/* Pestañas internas: Slots · Stats · Historial */}
        <div
          role="tablist"
          aria-label={farmList?.name ?? ''}
          style={{
            display: 'flex',
            background: 'var(--surface)',
            borderBottom: '1px solid var(--border)',
            flexShrink: 0,
          }}
        >
          {drawerTabs.map(tab => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`drawer-tab-${tab.id}`}
              aria-selected={activeTab === tab.id}
              aria-controls={`drawer-panel-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              style={{
                appearance: 'none', border: 'none',
                background: 'transparent',
                fontFamily: 'inherit',
                fontSize: '13px',
                fontWeight: activeTab === tab.id ? 500 : 400,
                color: activeTab === tab.id ? 'var(--text)' : 'var(--text-secondary)',
                cursor: 'pointer',
                padding: '10px 16px 8px',
                borderBottom: `2px solid ${activeTab === tab.id ? 'var(--accent)' : 'transparent'}`,
                transition: 'color var(--dur-fast), border-color var(--dur-fast)',
                position: 'relative', top: '1px',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div style={{
          flex: 1, overflowY: 'auto',
          padding: '16px 20px',
        }}>
          <div
            role="tabpanel"
            id={`drawer-panel-${activeTab}`}
            aria-labelledby={`drawer-tab-${activeTab}`}
          >
            {activeTab === 'slots' && (
              <SlotsPanel
                farmList={farmList}
                worldId={worldId}
                slots={slots}
                loading={loadingSlots}
                onRefresh={loadSlots}
                worldServer={worldServer}
                tribe={tribe}
              />
            )}
            {activeTab === 'stats' && (
              <StatsPanel farmList={farmList} slots={slots} />
            )}
            {activeTab === 'history' && (
              <HistoryPanel
                farmList={farmList}
                worldId={worldId}
              />
            )}
          </div>
        </div>

        {/* Footer: SendFeedback + "Enviar ahora" */}
        <div style={{
          padding: '10px 20px 12px',
          borderTop: '1px solid var(--border)',
          background: 'var(--surface)',
          flexShrink: 0,
        }}>
          <SendFeedback result={lastSendResult} t={t} />
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={handleSendNow}
              disabled={sending}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                height: '32px', padding: '0 14px',
                border: '1px solid var(--border-strong)',
                background: 'var(--surface)', color: 'var(--text)',
                borderRadius: 'var(--radius-sm)',
                cursor: sending ? 'not-allowed' : 'pointer',
                fontSize: '13px', fontFamily: 'inherit',
                opacity: sending ? 0.6 : 1,
                transition: 'background var(--dur-fast) var(--ease)',
              }}
              className="hover:bg-[var(--surface-2)]"
            >
              {sending ? <Spinner size={12} /> : <IconSend size={13} />}
              {t('drawer.sendNow')}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
