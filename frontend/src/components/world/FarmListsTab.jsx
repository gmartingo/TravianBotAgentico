/**
 * FarmListsTab — V4 Listas de vacas.
 *
 * Estados:
 *  - loading   : skeleton de filas agrupadas
 *  - empty     : empty state + CTA "Sincronizar desde Travian"
 *  - syncing   : banner informativo no-bloqueante encima de la tabla
 *  - error     : toast (showToast) + reintentar vía onSyncNow
 *  - con datos : grupos por aldea + tabla (desktop) / tarjetas (móvil)
 *
 * Props:
 *  - worldId      {number}
 *  - farmLists    {Array}    respuesta GET /farm/worlds/:id/farm-lists
 *  - loading      {boolean}  fetch inicial en vuelo
 *  - onSyncNow    {Function} dispara POST /farm-lists/read
 *  - syncing      {boolean}  POST /read en vuelo
 *  - lastSyncTime {string|null} ISO de la última sincronización
 *  - schedulers   {Array}    para resolver scheduler_id → nombre
 *  - onOpenDrawer {Function(farmList)} abre el drawer V5
 */
import { useEffect, useRef } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { Spinner } from '../ui/uiUtils.jsx'

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Tiempo relativo: "hace 3 min", "hace 2 h", "hace 1 d" */
function relativeTime(isoString, t) {
  if (!isoString) return '—'
  const diff = Math.floor((Date.now() - new Date(isoString)) / 1000)
  if (diff < 60) return `hace ${diff}s`
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`
  return `hace ${Math.floor(diff / 86400)} d`
}

/** Agrupa farm lists por (village_name, village_x, village_y) */
function groupByVillage(farmLists) {
  const groups = new Map()
  for (const fl of farmLists) {
    const key = `${fl.village_name ?? '?'}|${fl.village_x ?? 0}|${fl.village_y ?? 0}`
    if (!groups.has(key)) {
      groups.set(key, {
        name: fl.village_name ?? '?',
        x: fl.village_x ?? 0,
        y: fl.village_y ?? 0,
        lists: [],
      })
    }
    groups.get(key).lists.push(fl)
  }
  return Array.from(groups.values())
}

/** Cuenta slots en cooldown (con sonda pendiente) */
function probeCount(farmList) {
  if (!farmList.slots) return 0
  return farmList.slots.filter(s => s.disabled_by_bot && s.cooldown_seconds > 0).length
}

/** Calcula slots activos / total */
function slotStats(farmList) {
  if (!farmList.slots) return { active: 0, total: 0 }
  const total = farmList.slots.length
  const active = farmList.slots.filter(s => s.is_active).length
  return { active, total }
}

/** Formatea número con separador de miles (puntos) */
function fmtNum(n) {
  if (n == null || n === 0) return '—'
  return new Intl.NumberFormat('es').format(Math.round(n))
}

// ── Iconos ────────────────────────────────────────────────────────────────────

function IconSync({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-.08-8.1" />
    </svg>
  )
}

function IconList({ size = 48 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" />
      <line x1="3" y1="12" x2="3.01" y2="12" />
      <line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  )
}

function IconWarning({ size = 10 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  )
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SkeletonRow() {
  const pulse = {
    background: 'var(--surface-2)',
    borderRadius: 'var(--radius-sm)',
    animation: 'skeleton-pulse 1.4s ease-in-out infinite',
  }
  return (
    <tr>
      <td style={{ padding: '10px 14px' }}>
        <div style={{ ...pulse, height: '13px', width: '120px' }} />
      </td>
      <td style={{ padding: '10px 14px' }}>
        <div style={{ ...pulse, height: '13px', width: '50px' }} />
      </td>
      <td style={{ padding: '10px 14px' }}>
        <div style={{ ...pulse, height: '13px', width: '100px' }} />
      </td>
      <td style={{ padding: '10px 14px' }}>
        <div style={{ ...pulse, height: '13px', width: '70px' }} />
      </td>
      <td style={{ padding: '10px 14px', textAlign: 'end' }}>
        <div style={{ ...pulse, height: '13px', width: '50px', marginInlineStart: 'auto' }} />
      </td>
      <td style={{ padding: '10px 14px', width: '24px' }} />
    </tr>
  )
}

function SkeletonGroup() {
  const pulse = {
    background: 'var(--surface-2)',
    borderRadius: 'var(--radius-sm)',
    animation: 'skeleton-pulse 1.4s ease-in-out infinite',
  }
  return (
    <div style={{ marginBottom: '28px' }}>
      <div style={{ ...pulse, height: '14px', width: '140px', marginBottom: '12px' }} />
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
      }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <tbody>
            <SkeletonRow />
            <SkeletonRow />
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Tarjeta móvil de farm list ─────────────────────────────────────────────

function FarmListCard({ farmList, schedulerName, onOpen }) {
  const { t } = useI18n()
  const { active, total } = slotStats(farmList)
  const probes = probeCount(farmList)
  const noActive = active === 0 && total > 0

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onOpen()}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '12px 14px',
        cursor: 'pointer',
        marginBottom: '8px',
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        transition: 'background var(--dur-fast) var(--ease)',
      }}
      className="hover:bg-[var(--surface-2)]"
    >
      {/* Nombre + probe badge */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '14px', fontWeight: 500 }}>{farmList.name}</span>
          {probes > 0 && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: '4px',
              background: 'var(--accent-subtle)', color: 'var(--accent-text)',
              borderRadius: 'var(--radius-full)', padding: '1px 7px',
              fontSize: '11px', fontWeight: 500,
            }}>
              <IconWarning size={9} />
              {t('farmLists.probesLabel').replace('{n}', probes)}
            </span>
          )}
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '3px' }}>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontVariantNumeric: 'tabular-nums',
            color: noActive ? 'var(--danger)' : 'var(--text)',
          }}>
            {active}/{total}
          </span>
          {' '}slots
          {schedulerName && (
            <span style={{ marginInlineStart: '8px', color: 'var(--text-tertiary)' }}>
              · {schedulerName}
            </span>
          )}
        </div>
      </div>
      <span style={{ color: 'var(--text-tertiary)', fontSize: '18px', flexShrink: 0 }}>›</span>
    </div>
  )
}

// ── Fila de tabla desktop de farm list ────────────────────────────────────────

function FarmListRow({ farmList, schedulerName, onOpen }) {
  const { t } = useI18n()
  const { active, total } = slotStats(farmList)
  const probes = probeCount(farmList)
  const noActive = active === 0 && total > 0
  const recPerSend = farmList.avg_bounty_per_send ?? null
  const lastSend = farmList.last_send_time ?? null

  return (
    <tr
      id={`farm-list-row-${farmList.id}`}
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onOpen()}
      style={{ cursor: 'pointer' }}
      onTransitionEnd={e => { if (e.currentTarget.dataset.highlight) delete e.currentTarget.dataset.highlight }}
    >
      {/* Nombre */}
      <td style={{ padding: '10px 14px', fontSize: '13px' }}>
        <span>{farmList.name}</span>
        {probes > 0 && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '4px',
            background: 'var(--accent-subtle)', color: 'var(--accent-text)',
            borderRadius: 'var(--radius-full)', padding: '1px 7px',
            fontSize: '11px', fontWeight: 500,
            marginInlineStart: '6px',
          }}>
            <IconWarning size={9} />
            {t('farmLists.probesLabel').replace('{n}', probes)}
          </span>
        )}
      </td>

      {/* Slots */}
      <td style={{ padding: '10px 14px' }}>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '13px',
          fontVariantNumeric: 'tabular-nums',
          color: noActive ? 'var(--danger)' : 'var(--success)',
        }}>
          {active} / {total}
        </span>
      </td>

      {/* Scheduler */}
      <td style={{ padding: '10px 14px', fontSize: '12px' }}>
        {schedulerName
          ? <span>{schedulerName}</span>
          : <span style={{ color: 'var(--text-disabled)' }}>{t('farmLists.noScheduler')}</span>
        }
      </td>

      {/* Último envío */}
      <td style={{ padding: '10px 14px', fontSize: '12px', color: 'var(--text-secondary)' }}>
        {relativeTime(lastSend)}
      </td>

      {/* Rec/env */}
      <td style={{ padding: '10px 14px', textAlign: 'end' }}>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          fontVariantNumeric: 'tabular-nums',
          color: 'var(--text-secondary)',
        }}>
          {fmtNum(recPerSend)}
        </span>
      </td>

      {/* Flecha */}
      <td style={{
        padding: '10px 14px',
        paddingInlineStart: 0,
        textAlign: 'end',
        color: 'var(--text-tertiary)',
        fontSize: '16px',
        width: '24px',
      }}>
        ›
      </td>
    </tr>
  )
}

// ── Grupo de aldea ────────────────────────────────────────────────────────────

function VillageGroup({ village, schedulers, onOpenDrawer }) {
  const { t } = useI18n()

  function getSchedulerName(schedulerId) {
    if (!schedulerId) return null
    const s = schedulers.find(sc => sc.id === schedulerId)
    return s?.name ?? null
  }

  return (
    <div style={{ marginBottom: '28px' }}>
      {/* Cabecera del grupo */}
      <div style={{
        fontSize: '13px',
        fontWeight: 500,
        color: 'var(--text-secondary)',
        marginBottom: '8px',
        paddingBottom: '6px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'baseline',
        gap: '6px',
      }}>
        <span>{village.name}</span>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          color: 'var(--text-tertiary)',
        }}>
          ({village.x},{village.y})
        </span>
      </div>

      {/* Tabla desktop */}
      <table style={{
        width: '100%',
        borderCollapse: 'collapse',
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
      }}
        className="hidden md:table"
      >
        <thead>
          <tr>
            <th scope="col" style={{
              background: 'var(--surface-2)',
              fontSize: '11px', fontWeight: 500,
              color: 'var(--text-secondary)',
              textTransform: 'uppercase', letterSpacing: '.04em',
              padding: '8px 14px', textAlign: 'start',
              borderBottom: '1px solid var(--border)',
            }}>
              {t('farmLists.table.name')}
            </th>
            <th scope="col" style={{
              background: 'var(--surface-2)',
              fontSize: '11px', fontWeight: 500,
              color: 'var(--text-secondary)',
              textTransform: 'uppercase', letterSpacing: '.04em',
              padding: '8px 14px', textAlign: 'start',
              borderBottom: '1px solid var(--border)',
            }}>
              {t('farmLists.table.slots')}
            </th>
            <th scope="col" style={{
              background: 'var(--surface-2)',
              fontSize: '11px', fontWeight: 500,
              color: 'var(--text-secondary)',
              textTransform: 'uppercase', letterSpacing: '.04em',
              padding: '8px 14px', textAlign: 'start',
              borderBottom: '1px solid var(--border)',
            }}>
              {t('farmLists.table.scheduler')}
            </th>
            <th scope="col" style={{
              background: 'var(--surface-2)',
              fontSize: '11px', fontWeight: 500,
              color: 'var(--text-secondary)',
              textTransform: 'uppercase', letterSpacing: '.04em',
              padding: '8px 14px', textAlign: 'start',
              borderBottom: '1px solid var(--border)',
            }}>
              {t('farmLists.table.lastSend')}
            </th>
            <th scope="col" style={{
              background: 'var(--surface-2)',
              fontSize: '11px', fontWeight: 500,
              color: 'var(--text-secondary)',
              textTransform: 'uppercase', letterSpacing: '.04em',
              padding: '8px 14px', textAlign: 'end',
              borderBottom: '1px solid var(--border)',
            }}>
              {t('farmLists.table.recPerSend')}
            </th>
            <th scope="col" style={{
              background: 'var(--surface-2)',
              borderBottom: '1px solid var(--border)',
              width: '24px',
            }} />
          </tr>
        </thead>
        <tbody>
          {village.lists.map(fl => (
            <FarmListRow
              key={fl.id}
              farmList={fl}
              schedulerName={getSchedulerName(fl.scheduler_id)}
              onOpen={() => onOpenDrawer(fl)}
            />
          ))}
        </tbody>
      </table>

      {/* Tarjetas móvil */}
      <div className="md:hidden">
        {village.lists.map(fl => (
          <FarmListCard
            key={fl.id}
            farmList={fl}
            schedulerName={getSchedulerName(fl.scheduler_id)}
            onOpen={() => onOpenDrawer(fl)}
          />
        ))}
      </div>
    </div>
  )
}

// ── FarmListsTab (exportación principal) ──────────────────────────────────────

export function FarmListsTab({
  farmLists = [],
  loading = false,
  onSyncNow,
  syncing = false,
  lastSyncTime = null,
  schedulers = [],
  onOpenDrawer,
  highlightId = null,
  onClearHighlight,
}) {
  const { t } = useI18n()
  const isEmpty = !loading && farmLists.length === 0
  const groups = groupByVillage(farmLists)

  useEffect(() => {
    if (!highlightId) return
    const el = document.getElementById(`farm-list-row-${highlightId}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.dataset.highlight = '1'
    const timer = setTimeout(() => { delete el.dataset.highlight; onClearHighlight?.() }, 2000)
    return () => clearTimeout(timer)
  }, [highlightId, farmLists])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>

      {/* ── Encabezado de sección ── */}
      {!isEmpty && (
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '12px',
          marginBottom: '16px',
        }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: '17px', fontWeight: 600, letterSpacing: '-.01em' }}>
              {t('farmLists.title')}
            </div>
            {lastSyncTime && (
              <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                {t('farmLists.lastSync').replace('{t}', relativeTime(lastSyncTime))}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onSyncNow}
            disabled={syncing}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              height: '32px', padding: '0 14px',
              border: '1px solid var(--border-strong)',
              background: 'var(--surface)', color: 'var(--text)',
              borderRadius: 'var(--radius-sm)',
              cursor: syncing ? 'not-allowed' : 'pointer',
              fontSize: '13px', fontFamily: 'inherit',
              opacity: syncing ? 0.6 : 1,
              flexShrink: 0,
              transition: 'background var(--dur-fast) var(--ease)',
            }}
            className="hover:bg-[var(--surface-2)]"
          >
            {syncing ? <Spinner size={12} /> : <IconSync size={13} />}
            {syncing ? t('farmLists.syncing') : t('farmLists.syncNow')}
          </button>
        </div>
      )}

      {/* ── Banner de sincronización (no bloquea la UI) ── */}
      {syncing && !isEmpty && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '10px',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '10px 14px',
          marginBottom: '16px',
          fontSize: '13px', color: 'var(--text-secondary)',
        }}
          role="status"
          aria-live="polite"
        >
          <Spinner size={14} />
          {t('farmLists.syncing')}
        </div>
      )}

      {/* ── Estado: cargando (skeletons) ── */}
      {loading && (
        <>
          <style>{`
            @keyframes skeleton-pulse {
              0%, 100% { opacity: 1; }
              50% { opacity: 0.45; }
            }
          `}</style>
          <SkeletonGroup />
          <SkeletonGroup />
        </>
      )}

      {/* ── Estado: vacío ── */}
      {isEmpty && (
        <div style={{
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          padding: '64px 24px', textAlign: 'center', gap: '12px',
        }}>
          <span style={{ color: 'var(--text-disabled)', marginBottom: '4px' }}>
            <IconList size={48} />
          </span>
          <div style={{ fontSize: '17px', fontWeight: 600, letterSpacing: '-.01em' }}>
            {t('farmLists.empty.title')}
          </div>
          <div style={{
            fontSize: '14px', color: 'var(--text-secondary)',
            maxWidth: '280px', lineHeight: 1.5,
          }}>
            {t('farmLists.empty.sub')}
          </div>
          <button
            type="button"
            onClick={onSyncNow}
            disabled={syncing}
            style={{
              marginTop: '8px',
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              height: '36px', padding: '0 18px',
              background: 'var(--btn-primary-bg)',
              color: 'var(--btn-primary-text)',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              cursor: syncing ? 'not-allowed' : 'pointer',
              fontSize: '13px', fontFamily: 'inherit',
              opacity: syncing ? 0.6 : 1,
              transition: 'background var(--dur-fast) var(--ease)',
            }}
            className="hover:bg-[var(--btn-primary-hover)]"
          >
            {syncing ? <Spinner size={12} inverted /> : <IconSync size={12} />}
            {t('farmLists.empty.cta')}
          </button>
        </div>
      )}

      {/* ── Estado: con datos ── */}
      {!loading && !isEmpty && (
        <>
          {groups.map(village => (
            <VillageGroup
              key={`${village.name}|${village.x}|${village.y}`}
              village={village}
              schedulers={schedulers}
              onOpenDrawer={onOpenDrawer}
            />
          ))}
        </>
      )}
    </div>
  )
}
