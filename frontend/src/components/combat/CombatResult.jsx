/**
 * CombatResult — Panel de resultado del simulador.
 *
 * Reutiliza el componente TravianReport con la forma estándar Travian
 * (TÚ + DEFENSOR + STATS con neto por recurso). Mapea la respuesta del
 * endpoint /combat/simulate a las props normalizadas que TravianReport espera.
 *
 * Estructura del response del simulador (relevante aquí):
 *   attacker_wins, ratio, attacker_power, defender_power,
 *   attacker_troops[...], defender_troops[...],
 *   loot{ capacity, potential, resources_gained_from_animals },
 *   resource_losses{ attacker{ total_resources, breakdown[{tribe, ordinal, ..., total_cost{wood,clay,iron,crop}}] },
 *                    defender{ total_resources } },
 *   warnings[]
 */
import { useI18n } from '../../i18n/index.jsx'
import { TravianReport } from './TravianReport.jsx'

// Suma el desglose por recurso del atacante a partir de la lista breakdown
// que devuelve el simulador. Devuelve { wood, clay, iron, crop, total } o null.
function sumAttackerCostBreakdown(resourceLosses) {
  if (!resourceLosses?.attacker?.breakdown) return null
  const acc = { wood: 0, clay: 0, iron: 0, crop: 0, total: 0 }
  for (const entry of resourceLosses.attacker.breakdown) {
    const tc = entry.total_cost ?? {}
    acc.wood += Number(tc.wood ?? 0)
    acc.clay += Number(tc.clay ?? 0)
    acc.iron += Number(tc.iron ?? 0)
    acc.crop += Number(tc.crop ?? 0)
  }
  acc.total = acc.wood + acc.clay + acc.iron + acc.crop
  return acc
}

export function CombatResult({
  result,
  attackerTribeTroops,
  // Una entrada por formación defensora (defensor principal + refuerzos en
  // orden). Forma: [{ role:'defender'|'reinforcement', tribe, catalog, troopCount }].
  // troopCount = nº de tipos de tropa con qty>0 enviados al backend en esa
  // formación; sirve para volver a partir defender_troops del response.
  defenderFormations,
  // Compat: si llega defenderTribeTroops (legacy del optimizador, una sola
  // tribu sin refuerzos) se envuelve en una única formación "defender".
  defenderTribeTroops,
}) {
  const { t } = useI18n()

  if (!result) return null

  const attackerCostLoss = sumAttackerCostBreakdown(result.resource_losses)

  const effectiveFormations = defenderFormations
    ?? (defenderTribeTroops
      ? [{ role: 'defender', tribe: null, catalog: defenderTribeTroops, troopCount: null }]
      : [])

  return (
    <div style={{ marginTop: '16px' }}>
      <TravianReport
        attackerWins={result.attacker_wins === true}
        ratio={result.ratio}
        attackerPower={result.attacker_power}
        defenderPower={result.defender_power}
        attackerInfantryPower={result.attacker_infantry_power}
        attackerCavalryPower={result.attacker_cavalry_power}
        defenderInfantryPower={result.defender_infantry_power}
        defenderCavalryPower={result.defender_cavalry_power}
        attackerTroops={result.attacker_troops}
        defenderTroops={result.defender_troops}
        attackerTribeTroops={attackerTribeTroops}
        defenderFormations={effectiveFormations}
        animalLoot={result.loot?.resources_gained_from_animals ?? null}
        attackerCostLoss={attackerCostLoss}
        raidsCount={null}
      />

      {/* Warnings (si los hay, se muestran debajo del informe) */}
      {result.warnings && result.warnings.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '14px' }}>
          <div style={{
            fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)',
            textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: '2px',
          }}>
            {t('calc.result.warnings')}
          </div>
          {result.warnings.map((w, i) => (
            <div key={i} style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              padding: '4px 10px',
              background: 'var(--accent-subtle)',
              color: 'var(--accent-text)',
              borderRadius: 'var(--radius-full)',
              fontSize: '12px',
            }}>
              <span aria-hidden="true">⚠</span>
              {typeof w === 'string' ? w : w.message ?? JSON.stringify(w)}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
