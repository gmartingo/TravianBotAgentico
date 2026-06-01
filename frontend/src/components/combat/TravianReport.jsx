/**
 * TravianReport — Informe de combate con el formato estándar de Travian.
 *
 * 3 secciones:
 *  1. TÚ (atacante): fila de iconos + filas enviadas / pérdidas / supervivientes.
 *  2. DEFENSOR: misma estructura con iconos de animales/tropas defensoras.
 *  3. STATS: fuerza de combate, recursos perdidos por bando, botín animal por
 *     recurso, coste de tropas perdidas por recurso (w/c/i/c) y NETO por recurso.
 *
 * Se usa tanto desde el simulador (informe directo) como desde el optimizador
 * (en el detalle expandido de cada alternativa).
 *
 * Props normalizadas (no acopladas a la forma del backend):
 *   attackerWins        — boolean
 *   ratio               — number | null
 *   attackerPower       — number | null
 *   defenderPower       — number | null
 *   attackerTroops      — [{ ordinal, name, icon_url, quantity_initial, quantity_lost, quantity_survived }]
 *   defenderTroops      — misma estructura
 *   animalLoot          — { wood, clay, iron, crop, total } | null  (botín de animales)
 *   attackerCostLoss    — { wood, clay, iron, crop, total } | null  (coste recursos de bajas atacante)
 *   raidsCount          — number | null  (si Modo C, multiplicador a mostrar arriba como badge)
 */
import { useI18n } from '../../i18n/index.jsx'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n, lang = 'es') {
  if (n == null || isNaN(n)) return '—'
  return new Intl.NumberFormat(lang).format(Math.round(n))
}

// Rutas de los iconos del juego servidos por el backend en /static/icons.
// El proxy de Vite reescribe /api/* → backend, por eso anteponemos /api.
const RES_ICON_URL = {
  wood: '/api/static/icons/stat_wood.png',
  clay: '/api/static/icons/stat_clay.png',
  iron: '/api/static/icons/stat_iron.png',
  crop: '/api/static/icons/stat_crop.png',
}

/** Icono de recurso (madera/barro/hierro/cereal) servido desde assets del juego.
 *  Exportado para reutilizar en otros result panels (OptimizerResult, etc.). */
export function ResIcon({ res, size = 16, label }) {
  const url = RES_ICON_URL[res]
  if (!url) return null
  return (
    <img
      src={url}
      alt={label ?? res}
      title={label ?? res}
      style={{
        width: `${size}px`, height: `${size}px`,
        objectFit: 'contain', imageRendering: 'pixelated',
        display: 'inline-block', verticalAlign: 'middle',
        flexShrink: 0,
      }}
    />
  )
}

// Icono genérico del juego: name = nombre sin extensión bajo /static/icons/
// (p. ej. "stat_attack", "stat_def_infantry", "stat_carry", "stat_resources_sum").
function GameIcon({ name, size = 16, alt }) {
  return (
    <img
      src={`/api/static/icons/${name}.png`}
      alt={alt ?? name}
      title={alt ?? name}
      style={{
        width: `${size}px`, height: `${size}px`,
        objectFit: 'contain', imageRendering: 'pixelated',
        display: 'inline-block', verticalAlign: 'middle',
        flexShrink: 0,
      }}
    />
  )
}

function resolveIconUrl(iconUrl) {
  if (!iconUrl) return null
  if (iconUrl.startsWith('http')) return iconUrl
  return `/api${iconUrl}`
}

// ── Tabla de tropas (TÚ / DEFENSOR) ───────────────────────────────────────────

// Ancho fijo de la columna de etiqueta (cabe "Pérdidas" / "Enviadas";
// "Supervivientes" se trunca con ellipsis si hace falta). Las columnas de
// tropa NO llevan width: con table-layout: fixed se reparten el resto al
// 100 % del contenedor, sin scroll horizontal. Las cifras anchas se truncan
// con "…" antes que provocar overflow.
const LABEL_COL_W = 104

/**
 * Construye la lista de tropas a renderizar para el ATACANTE (1 sola tribu).
 *  - Si tribeTroops está dado (catálogo completo de la raza), itera SOBRE ÉL
 *    para que aparezcan TODAS las tropas posibles aunque entren con 0.
 *  - Si no se pasa, fallback al comportamiento previo (solo las con qty>0).
 */
function buildSourceTroops(troops, tribeTroops) {
  const data = troops ?? []
  if (!tribeTroops || tribeTroops.length === 0) {
    return data.filter(tr => (tr.quantity_initial ?? 0) > 0)
  }
  // Index por ordinal para acoplar datos del combate al catálogo.
  const byOrdinal = {}
  for (const tr of data) {
    if (tr.ordinal != null) byOrdinal[tr.ordinal] = tr
  }
  return tribeTroops
    .filter(m => m.ordinal != null)
    .map(m => {
      const matched = byOrdinal[m.ordinal]
      const iconFromCatalog = m.iconUrl
        ? m.iconUrl.replace(/^\/api/, '') // resolveIconUrl vuelve a anteponer /api
        : null
      return {
        ordinal: m.ordinal,
        name: matched?.name ?? m.name ?? `T${m.ordinal}`,
        icon_url: matched?.icon_url ?? iconFromCatalog,
        quantity_initial: matched?.quantity_initial ?? 0,
        quantity_lost: matched?.quantity_lost ?? 0,
        quantity_survived: matched?.quantity_survived ?? 0,
      }
    })
}

/**
 * Construye la lista de tropas a renderizar para UNA formación defensora.
 *  - subset: las tropas del backend que pertenecen a esta formación (slice).
 *  - catalog: catálogo completo de la tribu de la formación
 *    ([{ordinal, name, iconUrl}, ...]). Se itera para que aparezcan TODAS las
 *    tropas de la raza aunque entren con 0.
 *  - Si dos entradas del subset comparten ordinal (raro, pero posible si
 *    enviaras dos veces el mismo tipo), se agregan sumando qty.
 */
function buildFormationSourceTroops(subset, catalog) {
  const data = subset ?? []
  // Agregar por ordinal — todas las tropas de esta slice son de la misma tribu.
  // §17.10: null = cantidad desconocida (reporte perdido); se preserva como null
  // para que NumRow muestre '?' en lugar de 0.
  const byOrdinal = new Map()
  for (const tr of data) {
    if (tr.ordinal == null) continue
    const cur = byOrdinal.get(tr.ordinal) ?? {
      ordinal: tr.ordinal,
      name: tr.name,
      icon_url: tr.icon_url,
      // Semilla en 0 (cero CONOCIDO), no null: el acumulador solo pasa a null
      // si un valor ENTRANTE es null (reporte perdido). Arrancar en null haría
      // que addOrNull devolviera null siempre y todo se mostrara como '?'.
      quantity_initial: 0,
      quantity_lost: 0,
      quantity_survived: 0,
    }
    // Si el valor entrante es null (desconocido), el agregado pasa a null.
    // Si ambos son enteros, se suman.
    const addOrNull = (a, b) => (a === null || b === null) ? null : a + b
    cur.quantity_initial  = addOrNull(cur.quantity_initial,  tr.quantity_initial  ?? null)
    cur.quantity_lost     = addOrNull(cur.quantity_lost,     tr.quantity_lost     ?? null)
    cur.quantity_survived = addOrNull(cur.quantity_survived, tr.quantity_survived ?? null)
    byOrdinal.set(tr.ordinal, cur)
  }

  if (!catalog || catalog.length === 0) {
    // Sin catálogo: mostrar solo los que tienen alguna cantidad conocida (>0) o desconocida (null)
    return Array.from(byOrdinal.values()).filter(tr => tr.quantity_initial === null || tr.quantity_initial > 0)
  }

  return catalog
    .filter(m => m.ordinal != null)
    .map(m => {
      const matched = byOrdinal.get(m.ordinal)
      const iconFromCatalog = m.iconUrl
        ? m.iconUrl.replace(/^\/api/, '')
        : null
      return {
        ordinal: m.ordinal,
        name: matched?.name ?? m.name ?? `T${m.ordinal}`,
        icon_url: matched?.icon_url ?? iconFromCatalog,
        // §17.10: preservar null si la cantidad es desconocida
        quantity_initial:  matched ? matched.quantity_initial  : 0,
        quantity_lost:     matched ? matched.quantity_lost     : 0,
        quantity_survived: matched ? matched.quantity_survived : 0,
      }
    })
}

function TroopBand({ title, titleKey, accent, sourceTroops: precomputedSource, troops, tribeTroops, lang, t, fallbackLabelKey }) {
  // Defensor: el caller pasa sourceTroops ya partido por formación. Atacante:
  // pasa troops + tribeTroops y se construye aquí.
  const sourceTroops = precomputedSource ?? buildSourceTroops(troops, tribeTroops)
  const resolvedTitle = title ?? (titleKey ? t(titleKey) : '')

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      overflow: 'hidden',
      marginBottom: '14px',
    }}>
      {/* Banner */}
      <div style={{
        background: accent === 'attacker' ? 'rgba(201,53,44,.12)' : 'rgba(40,84,166,.12)',
        borderBottom: `1px solid ${accent === 'attacker' ? 'var(--danger)' : 'var(--accent)'}`,
        padding: '8px 14px',
        display: 'flex', alignItems: 'center', gap: '8px',
      }}>
        <span style={{ fontSize: '15px' }} aria-hidden="true">
          {accent === 'attacker' ? '⚔' : '🛡'}
        </span>
        <span style={{
          fontSize: '13px', fontWeight: 700,
          textTransform: 'uppercase', letterSpacing: '.06em',
          color: accent === 'attacker' ? 'var(--danger)' : 'var(--accent-text)',
        }}>
          {resolvedTitle}
        </span>
      </div>

      {sourceTroops.length === 0 ? (
        <div style={{ padding: '14px', fontSize: '13px', color: 'var(--text-tertiary)', textAlign: 'center' }}>
          {fallbackLabelKey ? t(fallbackLabelKey) : '—'}
        </div>
      ) : (
        <div>
          <table style={{
            borderCollapse: 'collapse',
            tableLayout: 'fixed',
            width: '100%',
          }}>
            <colgroup>
              <col style={{ width: `${LABEL_COL_W}px` }} />
              {/* Sin width en las columnas de tropa → table-layout:fixed las
                  reparte equitativamente con el espacio restante. */}
              {sourceTroops.map((tr, idx) => (
                <col key={`col-${tr.ordinal}-${idx}`} />
              ))}
            </colgroup>
            <thead>
              {/* Fila de iconos — alineados sobre los números porque la
                  tabla es fixed y cada col tiene ancho idéntico. */}
              <tr>
                <th style={{
                  textAlign: 'start',
                  padding: '8px 10px', background: 'var(--surface-2)',
                  borderBottom: '1px solid var(--border)',
                  fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)',
                  textTransform: 'uppercase', letterSpacing: '.04em',
                  boxSizing: 'border-box',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {t('calc.report.col.troop')}
                </th>
                {sourceTroops.map((tr, idx) => (
                  <th key={`icon-${tr.ordinal}-${idx}`} style={{
                    padding: '6px 2px', background: 'var(--surface-2)',
                    borderBottom: '1px solid var(--border)', textAlign: 'center',
                    boxSizing: 'border-box',
                    overflow: 'hidden',
                  }} title={tr.name ?? `T${tr.ordinal}`}>
                    {resolveIconUrl(tr.icon_url) ? (
                      <img src={resolveIconUrl(tr.icon_url)} alt={tr.name ?? `T${tr.ordinal}`}
                        style={{
                          width: '22px', height: '22px', objectFit: 'contain',
                          imageRendering: 'pixelated', display: 'inline-block', verticalAlign: 'middle',
                        }} />
                    ) : (
                      <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                        T{tr.ordinal}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <NumRow label={t('calc.report.row.sent')} troops={sourceTroops} pick="quantity_initial"
                color="var(--text)" lang={lang} />
              <NumRow label={t('calc.report.row.lost')} troops={sourceTroops} pick="quantity_lost"
                color="var(--danger)" sign="-" lang={lang} />
              <NumRow label={t('calc.report.row.survived')} troops={sourceTroops} pick="quantity_survived"
                color="var(--success)" bold lang={lang} />
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function NumRow({ label, troops, pick, color, sign, bold, lang }) {
  return (
    <tr>
      <td style={{
        padding: '7px 10px', borderBottom: '1px solid var(--border)',
        fontSize: '12px', color: 'var(--text-secondary)',
        background: 'var(--surface-2)', whiteSpace: 'nowrap',
        boxSizing: 'border-box',
        overflow: 'hidden', textOverflow: 'ellipsis',
      }}>
        {label}
      </td>
      {troops.map((tr, idx) => {
        const raw = tr[pick]
        // §17.10: null = reporte perdido (cantidades desconocidas) → mostrar '?'
        const isUnknown = raw === null || raw === undefined
        const v = isUnknown ? 0 : raw
        return (
          <td key={`${pick}-${tr.ordinal}-${idx}`} style={{
            padding: '6px 2px', borderBottom: '1px solid var(--border)', textAlign: 'center',
            fontSize: '12px', fontFamily: 'var(--font-mono)',
            fontVariantNumeric: 'tabular-nums', color: isUnknown ? 'var(--text-tertiary)' : (v > 0 ? color : 'var(--text-tertiary)'),
            fontWeight: bold && v > 0 ? 600 : 400,
            boxSizing: 'border-box',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {isUnknown ? '?' : (v > 0 ? (sign === '-' ? '−' : '') + fmt(v, lang) : '0')}
          </td>
        )
      })}
    </tr>
  )
}

// ── Stats panel ───────────────────────────────────────────────────────────────

function StatsTable({
  attackerPower, defenderPower,
  attackerInfantryPower, attackerCavalryPower,
  defenderInfantryPower, defenderCavalryPower,
  animalLoot, heroInventory, attackerCostLoss,
  lang, t,
}) {
  const resKeys = ['wood', 'clay', 'iron', 'crop']
  const hasHeroLoot = heroInventory != null

  function netFor(res) {
    const gain = (animalLoot?.[res] ?? 0) + (heroInventory?.[res] ?? 0)
    const cost = attackerCostLoss?.[res] ?? 0
    return gain - cost
  }
  const netTotal = resKeys.reduce((s, r) => s + netFor(r), 0)

  // Cuando el backend no expone el split inf/cav (versión antigua) hacemos
  // fallback al total para que la UI siga teniendo info útil.
  const aInf = attackerInfantryPower ?? null
  const aCav = attackerCavalryPower ?? null
  const dInf = defenderInfantryPower ?? null
  const dCav = defenderCavalryPower ?? null
  const hasSplit = (aInf != null) || (aCav != null) || (dInf != null) || (dCav != null)

  const rowStyle = { borderBottom: '1px solid var(--border)' }
  const labelTd = {
    padding: '8px 12px', fontSize: '12px', color: 'var(--text-secondary)',
    background: 'var(--surface-2)', whiteSpace: 'nowrap',
    width: '180px',
  }
  const valTd = {
    padding: '8px 12px', fontSize: '13px',
    fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
    color: 'var(--text)',
  }
  // Celda con icono del juego + número (atacante o defensor).
  function ValCell({ icon, value, color }) {
    return (
      <td style={{ ...valTd, color: color ?? 'var(--text)' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
          {icon}
          <span>{value != null ? fmt(value, lang) : '—'}</span>
        </span>
      </td>
    )
  }
  // Celda de porcentaje. El % en combate Travian es UNO solo: la proporción
  // inf/cav DEL ATACANTE (kirilloid: "cavalry part is X%, infantry part is Y%").
  // Ese mismo % se aplica a la defensa para mezclar def_inf y def_cav. Por eso
  // no hay un % distinto en el lado del defensor — la columna es única al final.
  function PctCell({ value, total }) {
    const pct = (total != null && total > 0 && value != null)
      ? Math.round((value / total) * 100)
      : null
    return (
      <td style={{
        ...valTd,
        textAlign: 'end',
        color: 'var(--text-tertiary)',
        fontSize: '12px',
        width: '64px',
        fontWeight: 600,
      }}>
        {pct != null ? `${pct}%` : '—'}
      </td>
    )
  }

  // Total del atacante = base para el % (la proporción rige el combate completo).
  const aTotal = (aInf ?? 0) + (aCav ?? 0)

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)', overflow: 'hidden',
    }}>
      <div style={{
        background: 'var(--surface-2)',
        padding: '8px 14px',
        borderBottom: '1px solid var(--border)',
      }}>
        <span style={{
          fontSize: '13px', fontWeight: 700,
          textTransform: 'uppercase', letterSpacing: '.06em',
          color: 'var(--text)',
        }}>
          {t('calc.report.stats.title')}
        </span>
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={rowStyle}>
            <th style={{ ...labelTd, fontWeight: 600 }}></th>
            <th style={{
              padding: '8px 12px', fontSize: '11px', fontWeight: 600,
              color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em',
              borderBottom: '1px solid var(--border)', textAlign: 'start',
            }}>
              {t('calc.report.stats.attacker')}
            </th>
            <th style={{
              padding: '8px 12px', fontSize: '11px', fontWeight: 600,
              color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em',
              borderBottom: '1px solid var(--border)', textAlign: 'start',
            }}>
              {t('calc.report.stats.defender')}
            </th>
            <th style={{
              padding: '8px 6px', fontSize: '11px', fontWeight: 600,
              color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em',
              borderBottom: '1px solid var(--border)', textAlign: 'end',
              width: '64px',
            }} title={t('calc.report.stats.pctTooltip')}>
              %
            </th>
          </tr>
        </thead>
        <tbody>
          {hasSplit ? (
            <>
              {/* Fila INFANTERÍA — atacante con stat_attack, defensor con stat_def_infantry.
                  La columna % final lleva la proporción inf/cav del ATACANTE,
                  que es el único % que rige el combate Travian (kirilloid). */}
              <tr style={rowStyle}>
                <td style={labelTd}>{t('calc.report.stats.infantry')}</td>
                <ValCell
                  icon={<GameIcon name="stat_attack" size={16} alt={t('calc.report.stats.attack')} />}
                  value={aInf}
                />
                <ValCell
                  icon={<GameIcon name="stat_def_infantry" size={16} alt={t('calc.report.stats.defInfantry')} />}
                  value={dInf}
                />
                <PctCell value={aInf} total={aTotal} />
              </tr>
              {/* Fila CABALLERÍA */}
              <tr style={rowStyle}>
                <td style={labelTd}>{t('calc.report.stats.cavalry')}</td>
                <ValCell
                  icon={<GameIcon name="stat_attack" size={16} alt={t('calc.report.stats.attack')} />}
                  value={aCav}
                />
                <ValCell
                  icon={<GameIcon name="stat_def_cavalry" size={16} alt={t('calc.report.stats.defCavalry')} />}
                  value={dCav}
                />
                <PctCell value={aCav} total={aTotal} />
              </tr>
            </>
          ) : (
            /* Fallback retro-compat: una sola fila con el total (sin %) */
            <tr style={rowStyle}>
              <td style={labelTd}>{t('calc.report.stats.combatStrength')}</td>
              <td style={valTd}>{attackerPower != null ? fmt(attackerPower, lang) : '—'}</td>
              <td style={valTd}>{defenderPower != null ? fmt(defenderPower, lang) : '—'}</td>
              <td style={valTd}></td>
            </tr>
          )}
        </tbody>
      </table>

      {/* Bloque por recurso: botín / coste / neto.
          table-layout:fixed + <colgroup> garantizan que cada icono de
          recurso (header) queda exactamente sobre su columna de cifras. */}
      <div style={{ borderTop: '1px solid var(--border)' }}>
        <table style={{
          width: '100%', borderCollapse: 'collapse',
          tableLayout: 'fixed',
        }}>
          <colgroup>
            <col style={{ width: '180px' }} />
            {resKeys.map(k => <col key={`gc-${k}`} style={{ width: 'auto' }} />)}
            <col style={{ width: '88px' }} />
          </colgroup>
          <thead>
            <tr>
              <th style={{ ...labelTd, fontWeight: 600 }}></th>
              {resKeys.map(k => (
                <th key={`h-${k}`} style={{
                  padding: '8px 6px', fontSize: '11px', fontWeight: 600,
                  color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em',
                  borderBottom: '1px solid var(--border)', textAlign: 'center',
                  background: 'var(--surface-2)',
                  boxSizing: 'border-box',
                }} title={t(`calc.res.${k}`)}>
                  <ResIcon res={k} size={18} label={t(`calc.res.${k}`)} />
                </th>
              ))}
              <th style={{
                padding: '8px 10px', fontSize: '11px', fontWeight: 600,
                color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '.04em',
                borderBottom: '1px solid var(--border)', textAlign: 'center',
                background: 'var(--surface-2)',
                whiteSpace: 'nowrap',
                boxSizing: 'border-box',
              }}>
                {/* Icono de "sumatorio" del juego + signo Σ para reforzar el significado */}
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', justifyContent: 'center' }}>
                  <GameIcon name="stat_resources_sum" size={16} alt={t('calc.report.stats.sum')} />
                  <span aria-hidden="true">Σ</span>
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {/* Botín animal — icono stat_carry (lo que has saqueado) */}
            <tr style={rowStyle}>
              <td style={labelTd}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <GameIcon name="stat_carry" size={16} alt={t('calc.report.stats.animalLoot')} />
                  {t('calc.report.stats.animalLoot')}
                </span>
              </td>
              {resKeys.map(k => (
                <td key={`g-${k}`} style={{ ...valTd, textAlign: 'center',
                  color: (animalLoot?.[k] ?? 0) > 0 ? 'var(--success)' : 'var(--text-tertiary)' }}>
                  {animalLoot?.[k] ? fmt(animalLoot[k], lang) : '0'}
                </td>
              ))}
              <td style={{ ...valTd, textAlign: 'end', fontWeight: 600,
                color: (animalLoot?.total ?? 0) > 0 ? 'var(--success)' : 'var(--text-tertiary)' }}>
                {animalLoot?.total ? fmt(animalLoot.total, lang) : '0'}
              </td>
            </tr>
            {/* Recursos por matar animales (van al inventario del héroe) */}
            {hasHeroLoot && (
              <tr style={rowStyle}>
                <td style={labelTd}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                    <GameIcon name="stat_carry" size={16} alt={t('calc.report.stats.heroLoot')} />
                    {t('calc.report.stats.heroLoot')}
                  </span>
                </td>
                {resKeys.map(k => (
                  <td key={`hl-${k}`} style={{ ...valTd, textAlign: 'center',
                    color: (heroInventory?.[k] ?? 0) > 0 ? 'var(--success)' : 'var(--text-tertiary)' }}>
                    {heroInventory?.[k] ? fmt(heroInventory[k], lang) : '0'}
                  </td>
                ))}
                <td style={{ ...valTd, textAlign: 'end', fontWeight: 600,
                  color: (heroInventory?.total ?? 0) > 0 ? 'var(--success)' : 'var(--text-tertiary)' }}>
                  {heroInventory?.total ? fmt(heroInventory.total, lang) : '0'}
                </td>
              </tr>
            )}
            {/* Coste tropas perdidas */}
            <tr style={rowStyle}>
              <td style={labelTd}>{t('calc.report.stats.troopsCost')}</td>
              {resKeys.map(k => (
                <td key={`c-${k}`} style={{ ...valTd, textAlign: 'center',
                  color: (attackerCostLoss?.[k] ?? 0) > 0 ? 'var(--danger)' : 'var(--text-tertiary)' }}>
                  {attackerCostLoss?.[k] ? `−${fmt(attackerCostLoss[k], lang)}` : '0'}
                </td>
              ))}
              <td style={{ ...valTd, textAlign: 'end', fontWeight: 600,
                color: (attackerCostLoss?.total ?? 0) > 0 ? 'var(--danger)' : 'var(--text-tertiary)' }}>
                {attackerCostLoss?.total ? `−${fmt(attackerCostLoss.total, lang)}` : '0'}
              </td>
            </tr>
            {/* Neto */}
            <tr style={{ background: 'var(--surface-2)' }}>
              <td style={{ ...labelTd, fontWeight: 700, color: 'var(--text)' }}>
                {t('calc.report.stats.net')}
              </td>
              {resKeys.map(k => {
                const v = netFor(k)
                return (
                  <td key={`n-${k}`} style={{ ...valTd, textAlign: 'center', fontWeight: 700,
                    color: v > 0 ? 'var(--success)' : v < 0 ? 'var(--danger)' : 'var(--text-tertiary)' }}>
                    {v === 0 ? '0' : (v > 0 ? '+' : '−') + fmt(Math.abs(v), lang)}
                  </td>
                )
              })}
              <td style={{ ...valTd, textAlign: 'end', fontWeight: 700,
                color: netTotal > 0 ? 'var(--success)' : netTotal < 0 ? 'var(--danger)' : 'var(--text-tertiary)' }}>
                {netTotal === 0 ? '0' : (netTotal > 0 ? '+' : '−') + fmt(Math.abs(netTotal), lang)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── TravianReport (raíz) ──────────────────────────────────────────────────────

export function TravianReport({
  attackerWins,
  ratio,
  attackerPower, defenderPower,
  // Split infantería/caballería del backend (post-fix). Si falta cae a la
  // fila única con attackerPower/defenderPower.
  attackerInfantryPower, attackerCavalryPower,
  defenderInfantryPower, defenderCavalryPower,
  attackerTroops, defenderTroops,
  // Catálogos completos por raza ([{ordinal, name, iconUrl}]).
  // Atacante: tribu única → un solo catálogo.
  // Defensor: lista de formaciones (defensor principal + refuerzos en orden).
  //   [{ role:'defender'|'reinforcement', tribe, catalog, troopCount }]
  // troopCount es el nº de tipos enviados al backend en esa formación; se usa
  // para partir defenderTroops (que el backend devuelve aplanado por orden).
  // Si llega `defenderTribeTroops` (legacy, sin refuerzos) se envuelve.
  attackerTribeTroops,
  defenderFormations,
  defenderTribeTroops,
  animalLoot,
  heroInventory,
  attackerCostLoss,
  raidsCount,
}) {
  const { t, lang } = useI18n()

  return (
    <div role="region" aria-label={t('calc.report.title')} style={{
      display: 'flex', flexDirection: 'column', gap: '0',
    }}>
      {/* Badge ganador + ratio + (multi-raid) N */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '12px',
        marginBottom: '14px', flexWrap: 'wrap',
      }}>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px',
          padding: '5px 14px', borderRadius: 'var(--radius-full)',
          background: attackerWins ? 'rgba(36,138,61,.12)' : 'rgba(201,53,44,.12)',
          border: `1px solid ${attackerWins ? 'var(--success)' : 'var(--danger)'}`,
        }}>
          <span style={{ fontSize: '15px' }}>{attackerWins ? '⚔' : '🛡'}</span>
          <span style={{
            fontSize: '14px', fontWeight: 600,
            color: attackerWins ? 'var(--success)' : 'var(--danger)',
          }}>
            {attackerWins ? t('calc.result.attackerWins') : t('calc.result.defenderWins')}
          </span>
        </div>
        {ratio != null && (
          <span style={{ fontSize: '13px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
            {t('calc.result.ratio', { ratio: Number(ratio).toFixed(2) })}
          </span>
        )}
        {raidsCount != null && (
          <span style={{
            marginLeft: 'auto',
            display: 'inline-flex', alignItems: 'center', gap: '6px',
            padding: '5px 12px', borderRadius: 'var(--radius-full)',
            background: 'var(--accent-subtle)',
            border: '1px solid var(--accent)',
            color: 'var(--accent-text)',
            fontSize: '13px', fontWeight: 600,
          }}>
            ×{fmt(raidsCount, lang)} {t('calc.report.raids')}
          </span>
        )}
      </div>

      {/* TÚ */}
      <TroopBand
        titleKey="calc.report.you"
        accent="attacker"
        troops={attackerTroops}
        tribeTroops={attackerTribeTroops}
        lang={lang} t={t}
      />

      {/* DEFENSOR + REFUERZOS — una banda por formación */}
      {(() => {
        const formations = defenderFormations
          ?? (defenderTribeTroops
            ? [{ role: 'defender', tribe: null, catalog: defenderTribeTroops, troopCount: null }]
            : [])

        // Si no hay info de formaciones, fallback: una sola banda con todos los
        // datos del backend (sin partir).
        if (!formations.length) {
          return (
            <TroopBand
              titleKey="calc.report.defender"
              accent="defender"
              troops={defenderTroops}
              tribeTroops={null}
              lang={lang} t={t}
              fallbackLabelKey="calc.report.noDefender"
            />
          )
        }

        const allTroops = defenderTroops ?? []
        // Cuando todas las formaciones traen troopCount, partimos la lista
        // del backend en bloques. Si alguna trae null (legacy), esa banda
        // recibe el array entero (caso una-sola-formación).
        const knowCounts = formations.every(f => Number.isInteger(f.troopCount))
        let cursor = 0
        // Contamos cuántas formaciones de refuerzo hay para numerar el título
        // solo cuando hay más de una.
        const reinforcementCount = formations.filter(f => f.role === 'reinforcement').length
        let reinforcementIdx = 0

        return formations.map((f, i) => {
          const subset = knowCounts
            ? allTroops.slice(cursor, cursor + f.troopCount)
            : allTroops
          if (knowCounts) cursor += f.troopCount

          const sourceTroops = buildFormationSourceTroops(subset, f.catalog)

          let title
          if (f.role === 'reinforcement') {
            reinforcementIdx += 1
            title = reinforcementCount > 1
              ? `${t('calc.report.reinforcement')} ${reinforcementIdx}`
              : t('calc.report.reinforcement')
          } else {
            title = t('calc.report.defender')
          }

          return (
            <TroopBand
              key={`def-band-${i}`}
              title={title}
              accent="defender"
              sourceTroops={sourceTroops}
              lang={lang} t={t}
              fallbackLabelKey="calc.report.noDefender"
            />
          )
        })
      })()}

      {/* STATS */}
      <StatsTable
        attackerPower={attackerPower} defenderPower={defenderPower}
        attackerInfantryPower={attackerInfantryPower}
        attackerCavalryPower={attackerCavalryPower}
        defenderInfantryPower={defenderInfantryPower}
        defenderCavalryPower={defenderCavalryPower}
        animalLoot={animalLoot}
        heroInventory={heroInventory}
        attackerCostLoss={attackerCostLoss}
        lang={lang} t={t}
      />
    </div>
  )
}
