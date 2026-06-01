/**
 * ReportPreview — Muestra la barra de metadata (coords/fecha/aldea),
 * el banner de duplicado condicional y el componente TravianReport.
 *
 * Gestiona el mapeo de props del backend → TravianReport (spec §14):
 *   animals[i].present → defenderTroops[i].quantity_initial
 *   animals[i].killed  → defenderTroops[i].quantity_lost
 *   animals[i].survived→ defenderTroops[i].quantity_survived
 *   attacker_troops[i].sent      → attackerTroops[i].quantity_initial
 *   attacker_troops[i].lost      → attackerTroops[i].quantity_lost
 *   attacker_troops[i].survived  → attackerTroops[i].quantity_survived
 *
 * Props:
 *   data          — respuesta de POST /attack-reports/parse
 *   lang          — string (idioma activo)
 *   onViewExisting — (id) => void — abre el drawer del reporte existente
 *   t             — función de traducción
 */
import { TravianReport } from '../combat/TravianReport.jsx'
import { formatDateVerbatim } from '../../utils/formatDateVerbatim.js'

function formatCoord(n) {
  // Coordenada con signo, guión largo − (U+2212) para negativos
  if (n == null) return '—'
  return n < 0 ? `−${Math.abs(n)}` : `${n}`
}

function formatCoords(x, y) {
  return `(${formatCoord(x)}|${formatCoord(y)})`
}

// attacked_at es verbatim (hora del servidor Travian) — no pasar por new Date()
function formatDate(isoStr) {
  return formatDateVerbatim(isoStr)
}

function mapAttackerTroops(attackerTroopsRaw) {
  if (!attackerTroopsRaw) return []
  return attackerTroopsRaw.map((t) => ({
    ordinal: t.troop_ordinal ?? t.ordinal ?? null,
    name: t.troop_name ?? t.name ?? `T${t.troop_ordinal ?? t.ordinal}`,
    icon_url: t.icon_url ?? null,
    quantity_initial: t.sent ?? 0,
    quantity_lost: t.lost ?? 0,
    quantity_survived: t.survived ?? (t.sent ?? 0) - (t.lost ?? 0),
  }))
}

function mapDefenderTroops(animalsRaw) {
  if (!animalsRaw) return []
  return animalsRaw.map((a) => ({
    ordinal: a.animal_ordinal ?? a.ordinal ?? null,
    name: a.animal_name ?? a.name ?? `A${a.animal_ordinal ?? a.ordinal}`,
    icon_url: a.icon_url ?? null,
    // §17.5 / §17.10: si present/killed/survived es null (reporte perdido),
    // preservar null para que TravianReport muestre '?' en lugar de 0.
    quantity_initial:  a.present  != null ? a.present  : null,
    quantity_lost:     a.killed   != null ? a.killed   : null,
    quantity_survived: a.survived != null ? a.survived : null,
  }))
}

function DuplicateBanner({ existingId, onView, t }) {
  return (
    <div
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '10px 14px',
        marginBottom: '12px',
        background: 'var(--accent-subtle)',
        border: '1px solid var(--accent)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '13px',
        color: 'var(--text)',
      }}
    >
      <span aria-hidden="true" style={{ fontSize: '16px', flexShrink: 0 }}>⚠</span>
      <span style={{ flex: 1 }}>
        {t('ar.dup.title')}
      </span>
      <button
        type="button"
        onClick={() => onView(existingId)}
        style={{
          background: 'none',
          border: 'none',
          padding: '0',
          cursor: 'pointer',
          fontFamily: 'inherit',
          fontSize: '13px',
          color: 'var(--accent-text)',
          textDecoration: 'underline',
          whiteSpace: 'nowrap',
          flexShrink: 0,
        }}
      >
        {t('ar.dup.link').replace('{id}', existingId)}
      </button>
    </div>
  )
}

export function ReportPreview({ data, lang, onViewExisting, t }) {
  if (!data) return null

  const attackerTroops = mapAttackerTroops(data.attacker_troops)
  const defenderTroops = mapDefenderTroops(data.animals)

  // Catálogos de la "raza" para que TravianReport muestre el ROSTER COMPLETO
  // (todos los iconos, incluso tipos con 0), igual que el reporte real de Travian.
  // Los datos ya vienen completos: el reporte lista toda la tabla de tropas/animales.
  const attackerCatalog = attackerTroops
    .filter((tr) => tr.ordinal != null)
    .map((tr) => ({ ordinal: tr.ordinal, name: tr.name, iconUrl: tr.icon_url }))
  const defenderCatalog = defenderTroops
    .filter((a) => a.ordinal != null)
    .map((a) => ({ ordinal: a.ordinal, name: a.name, iconUrl: a.icon_url }))

  const defenderFormations = defenderCatalog.length
    ? [{ role: 'defender', tribe: 'nature', catalog: defenderCatalog, troopCount: defenderTroops.length }]
    : []

  const bounty = data.bounty
    ? {
        wood: data.bounty.wood,
        clay: data.bounty.clay,
        iron: data.bounty.iron,
        crop: data.bounty.crop,
        total: (data.bounty.wood ?? 0) + (data.bounty.clay ?? 0) +
               (data.bounty.iron ?? 0) + (data.bounty.crop ?? 0),
      }
    : null

  // Coste en recursos de las tropas perdidas (lo calcula el backend con los
  // costes de entrenamiento por tribu+ordinal). Ya viene con total.
  const costLoss = data.attacker_cost_loss ?? null

  // Recursos ganados por matar animales (van al inventario del héroe).
  const heroLoot = data.hero_inventory
    ? {
        wood: data.hero_inventory.wood ?? 0,
        clay: data.hero_inventory.clay ?? 0,
        iron: data.hero_inventory.iron ?? 0,
        crop: data.hero_inventory.crop ?? 0,
        total: (data.hero_inventory.wood ?? 0) + (data.hero_inventory.clay ?? 0) +
               (data.hero_inventory.iron ?? 0) + (data.hero_inventory.crop ?? 0),
      }
    : null

  const totalLost = attackerTroops.reduce((s, t) => s + (t.quantity_lost ?? 0), 0)
  // TravianReport espera attackerWins. En ataques a animales, el atacante casi
  // siempre gana. El reporte no lo indica explícitamente — lo inferimos por si
  // quedan supervivientes atacantes (si hay al menos 1, el atacante ganó).
  // Con quantity_survived=null (reporte perdido) se considera como 0.
  const anyAttackerSurvived = attackerTroops.some(t => (t.quantity_survived ?? 0) > 0)
  const attackerWins = totalLost === 0 || anyAttackerSurvived

  const coordStr = formatCoords(data.coord_x_dest, data.coord_y_dest)
  const dateStr  = formatDate(data.attacked_at)
  const village  = data.origin_village_name ?? '—'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
      {/* Banner duplicado */}
      {data.already_exists && data.existing_id != null && (
        <DuplicateBanner
          existingId={data.existing_id}
          onView={onViewExisting}
          t={t}
        />
      )}

      {/* Barra de metadata (coords · fecha · aldea) */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '4px 12px',
        padding: '8px 0 12px',
        fontSize: '13px',
        color: 'var(--text-secondary)',
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)', fontWeight: 600 }}>
          {coordStr}
        </span>
        <span aria-hidden="true" style={{ color: 'var(--border-strong)' }}>·</span>
        <span>{dateStr}</span>
        <span aria-hidden="true" style={{ color: 'var(--border-strong)' }}>·</span>
        <span>
          {t('ar.preview.from')}{' '}
          <span style={{ fontStyle: 'italic' }}>&ldquo;{village}&rdquo;</span>
        </span>
      </div>

      {/* TravianReport — roster completo (catálogos) + recursos del héroe */}
      <TravianReport
        attackerWins={attackerWins}
        ratio={null}
        attackerPower={null}
        defenderPower={null}
        attackerTroops={attackerTroops}
        defenderTroops={defenderTroops}
        attackerTribeTroops={attackerCatalog}
        defenderFormations={defenderFormations}
        animalLoot={bounty}
        heroInventory={heroLoot}
        attackerCostLoss={costLoss}
        raidsCount={null}
      />
    </div>
  )
}
