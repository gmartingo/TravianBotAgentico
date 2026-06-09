/**
 * CombatCalculator — Componente raíz del simulador de combate.
 *
 * Gestiona el estado global:
 *  - Tribu y tropas del atacante
 *  - Tribu y tropas del defensor (NATURE por defecto)
 *  - Lista de refuerzos del defensor
 *  - Controles (tipo de ataque, muro, smithy, héroe, etc.)
 *  - Estado de la simulación (idle / loading / resultado / error)
 *
 * Arquitectura:
 *  - Carga iconos de tropas para cada tribu distinta presente
 *  - Construye el body del POST /combat/simulate según la spec
 *  - Delega renderizado a ArmyPanel (x3+), TribeBar, TroopGrid y CombatResult
 *
 * Layout aprobado (Travian calculator style):
 *  [ ArmyPanel atacante ]
 *  [ ArmyPanel defensor ]
 *  [ ArmyPanel refuerzo (0-n) ]
 *  [ Botón "Añadir refuerzo" ]
 *  [ Botón "SIMULAR" ]
 *  [ CombatResult ]
 */
import { useState, useEffect, useCallback, useId } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api, ApiError } from '../../api/client.js'
import { Spinner, showToast } from '../ui/uiUtils.jsx'
import { ArmyPanel } from './ArmyPanel.jsx'
import { CombatResult } from './CombatResult.jsx'
import { OptimizerPanel } from './OptimizerPanel.jsx'
import { OptimizerResult } from './OptimizerResult.jsx'

// ── Constantes ────────────────────────────────────────────────────────────────

// Orden de tribus para el atacante
const ATTACKER_TRIBES = [
  { id: 'romans',    labelKey: 'calc.tribe.romans' },
  { id: 'teutons',   labelKey: 'calc.tribe.teutons' },
  { id: 'gauls',     labelKey: 'calc.tribe.gauls' },
  { id: 'egyptians', labelKey: 'calc.tribe.egyptians' },
  { id: 'huns',      labelKey: 'calc.tribe.huns' },
  { id: 'spartans',  labelKey: 'calc.tribe.spartans' },
  { id: 'vikings',   labelKey: 'calc.tribe.vikings' },
]

// Orden de tribus para el defensor (NATURE primero)
const DEFENDER_TRIBES = [
  { id: 'nature',    labelKey: 'calc.tribe.nature' },
  ...ATTACKER_TRIBES,
]

// Estado inicial de valores de tropas: objeto vacío (se puebla cuando llegan los iconos)
function emptyTroopValues() {
  return {}
}

// Estado inicial de un panel de defensor/refuerzo
function makeDefenderState(tribe = 'nature') {
  return {
    id: Date.now() + Math.random(), // key única para React
    tribe,
    troopValues: emptyTroopValues(),
    wallLevel: 0,
    stonemasonLevel: 0,
    allianceBonus: 0,
    heroDefPoints: 0,
    heroDefBonusPct: 0,
  }
}

// ── Función de carga de iconos ────────────────────────────────────────────────
// Devuelve { [ordinal]: { ordinal, name?, iconUrl } }
// La API de catálogo no devuelve el nombre localizado de las tropas en iconos,
// solo el icon_id, ordinal y url — se muestra el ordinal como fallback.

async function loadTroops(tribe) {
  const data = await api.getCatalogIcons({ icon_type: 'troop', tribe })
  const icons = data?.icons ?? []
  // Ordenar por ordinal
  icons.sort((a, b) => (a.ordinal ?? 0) - (b.ordinal ?? 0))
  return icons.map(icon => ({
    ordinal: icon.ordinal,
    name: icon.name ?? null,
    iconUrl: icon.url
      ? (icon.url.startsWith('http') ? icon.url : `/api${icon.url}`)
      : null,
  }))
}

// ── Hook: tropas por tribu (con caché en memoria de sesión) ───────────────────

const troopsCache = {}

function useTribesTroops(tribes) {
  // tribes = array de tribeId únicos que necesitamos cargar
  const [troopsMap, setTroopsMap] = useState({}) // { tribeId: [{ ordinal, name, iconUrl }] }

  useEffect(() => {
    const missing = tribes.filter(t => t && !troopsMap[t] && !troopsCache[t])
    if (missing.length === 0) return

    // Marcar como "cargando" para evitar dobles peticiones
    missing.forEach(t => { troopsCache[t] = [] })

    Promise.all(missing.map(async tribe => {
      try {
        const troops = await loadTroops(tribe)
        troopsCache[tribe] = troops
        return [tribe, troops]
      } catch {
        troopsCache[tribe] = []
        return [tribe, []]
      }
    })).then(results => {
      setTroopsMap(prev => {
        const next = { ...prev }
        results.forEach(([tribe, troops]) => { next[tribe] = troops })
        return next
      })
    })
  }, [tribes.join(',')])

  // Completar con caché ya disponible
  const merged = { ...troopsMap }
  tribes.forEach(t => {
    if (t && !merged[t] && troopsCache[t]) {
      merged[t] = troopsCache[t]
    }
  })

  return merged
}

// ── CombatCalculator ──────────────────────────────────────────────────────────

export function CombatCalculator() {
  const { t } = useI18n()

  // ── Modo: simulador | optimizador ─────────────────────────────────────────
  const [mode, setMode] = useState('simulator') // 'simulator' | 'optimizer'

  // ── Estado atacante ────────────────────────────────────────────────────────
  const [atkTribe, setAtkTribe] = useState('romans')
  const [atkTroopValues, setAtkTroopValues] = useState(emptyTroopValues())
  const [atkType, setAtkType] = useState('raid')
  const [atkAllianceBonus, setAtkAllianceBonus] = useState(0)
  const [atkArtifact, setAtkArtifact] = useState('none')
  const [atkHeroPoints, setAtkHeroPoints] = useState(0)
  const [atkHeroBonusPct, setAtkHeroBonusPct] = useState(0)

  // ── Estado defensor (principal) ────────────────────────────────────────────
  const [defState, setDefState] = useState(() => makeDefenderState('nature'))

  // ── Refuerzos adicionales ──────────────────────────────────────────────────
  const [reinforcements, setReinforcements] = useState([])

  // ── Simulación ─────────────────────────────────────────────────────────────
  const [simulating, setSimulating] = useState(false)
  const [result, setResult] = useState(null) // respuesta de la API o null

  // ── Optimizador ─────────────────────────────────────────────────────────────
  const [optimizing, setOptimizing] = useState(false)
  const [optResult, setOptResult] = useState(null)
  const [optimizerInputMode, setOptimizerInputMode] = useState('multi_troop') // 'multi_troop' | 'army_sim' | 'multi_raid'
  const [optimizerMinNetGainPct, setOptimizerMinNetGainPct] = useState(20) // default multi_troop
  // Tribu del atacante compartida entre simulador y optimizador
  // (el optimizador usa atkTribe y puede cambiarlo con onAtkTribeChange)

  // ── Cargar tropas de todas las tribus presentes ────────────────────────────
  const uniqueTribes = [
    atkTribe,
    'nature', // siempre necesario para el optimizador
    defState.tribe,
    ...reinforcements.map(r => r.tribe),
  ].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i)

  const troopsMap = useTribesTroops(uniqueTribes)

  // ── Helpers de mutación de defensor ───────────────────────────────────────

  function updateDefState(partial) {
    setDefState(prev => ({ ...prev, ...partial }))
  }

  function updateDefTroopValue(ordinal, field, value) {
    setDefState(prev => ({
      ...prev,
      troopValues: {
        ...prev.troopValues,
        [ordinal]: { ...(prev.troopValues[ordinal] ?? { qty: 0, smithy: 0 }), [field]: value },
      },
    }))
  }

  // ── Helpers de mutación de refuerzo ───────────────────────────────────────

  function addReinforcement() {
    setReinforcements(prev => [...prev, makeDefenderState('nature')])
  }

  function removeReinforcement(id) {
    setReinforcements(prev => prev.filter(r => r.id !== id))
  }

  function updateReinforcement(id, partial) {
    setReinforcements(prev => prev.map(r => r.id === id ? { ...r, ...partial } : r))
  }

  function updateReinforcementTroop(id, ordinal, field, value) {
    setReinforcements(prev => prev.map(r => {
      if (r.id !== id) return r
      return {
        ...r,
        troopValues: {
          ...r.troopValues,
          [ordinal]: { ...(r.troopValues[ordinal] ?? { qty: 0, smithy: 0 }), [field]: value },
        },
      }
    }))
  }

  // ── Construir body del request ─────────────────────────────────────────────

  function buildRequestBody() {
    const atkTroops = troopsMap[atkTribe] ?? []
    const attackerTroops = atkTroops
      .filter(t => Number(atkTroopValues[t.ordinal]?.qty) > 0)
      .map(t => ({
        ordinal: t.ordinal,
        quantity: Number(atkTroopValues[t.ordinal]?.qty ?? 0),
        smithy_level: Number(atkTroopValues[t.ordinal]?.smithy ?? 0),
      }))

    const artifactMap = { none: 1.0, fast1_5: 1.5, fast2: 2.0 }

    // DefenderRequest: solo tribe, troops, hero_*, village_resources, artifacts
    // wall_level y stonemason_level van en el objeto raíz "wall" (WallRequest)
    const buildDefender = (d) => {
      const dTroops = troopsMap[d.tribe] ?? []
      return {
        tribe: d.tribe,
        troops: dTroops
          .filter(t => Number(d.troopValues[t.ordinal]?.qty) > 0)
          .map(t => ({
            tribe: d.tribe,
            ordinal: t.ordinal,
            quantity: Number(d.troopValues[t.ordinal]?.qty ?? 0),
            smithy_level: Number(d.troopValues[t.ordinal]?.smithy ?? 0),
          })),
        hero_defense_points: d.heroDefPoints ?? 0,
        hero_defense_bonus_percent: d.heroDefBonusPct ?? 0,
      }
    }

    return {
      attacker: {
        tribe: atkTribe,
        attack_type: atkType,
        troops: attackerTroops,
        hero_attack_points: atkHeroPoints ?? 0,
        hero_attack_bonus_percent: atkHeroBonusPct ?? 0,
        alliance_bonus: atkAllianceBonus ?? 0,
        artifacts: {
          fast_troops: artifactMap[atkArtifact] ?? 1.0,
          diet: 1.0,
        },
        morale: 100,
      },
      defenders: [
        buildDefender(defState),
        ...reinforcements.map(buildDefender),
      ],
      // wall es global (del pueblo atacado), no por defensor
      wall: {
        wall_level: defState.wallLevel ?? 0,
        stonemason_level: defState.stonemasonLevel ?? 0,
      },
    }
  }

  // ── Optimizador ────────────────────────────────────────────────────────────

  async function handleOptimize(body) {
    setOptimizing(true)
    try {
      const res = await api.combat.optimize(body)
      setOptResult(res)
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : t('calc.optimizer.error')
      showToast(typeof msg === 'string' ? msg : t('calc.optimizer.error'))
    } finally {
      setOptimizing(false)
    }
  }

  // ── Simulación ─────────────────────────────────────────────────────────────

  async function handleSimulate() {
    setSimulating(true)
    try {
      const body = buildRequestBody()
      const res = await api.combat.simulate(body)
      // Capturamos qué formaciones envió el usuario y cuántos tipos de tropa
      // tiene cada una. El backend devuelve defender_troops aplanado en el
      // mismo orden que el request, así podemos volver a partirlo por
      // formación para renderizar la tabla principal y una por refuerzo.
      const formations = body.defenders.map((d, i) => ({
        role: i === 0 ? 'defender' : 'reinforcement',
        tribe: d.tribe,
        catalog: troopsMap[d.tribe] ?? [],
        troopCount: d.troops.length,
      }))
      setResult({ response: res, defenderFormations: formations })
    } catch (e) {
      if (e instanceof ApiError) {
        const d = e.detail
        // Pydantic devuelve array de errores — mostrar el primero legible
        const msg = Array.isArray(d)
          ? d.map(err => `${err.loc?.slice(-1)[0] ?? ''}: ${err.msg}`).join(' | ')
          : (typeof d === 'string' ? d : t('calc.error.simulate'))
        showToast(msg)
      } else {
        showToast(t('calc.error.simulate'))
      }
    } finally {
      setSimulating(false)
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div style={{
      maxWidth: '720px',
      margin: '0 auto',
      display: 'flex',
      flexDirection: 'column',
      gap: '0',
    }}>
      {/* ── Cabecera: título + toggle de modo ── */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        marginBottom: '16px',
        flexWrap: 'wrap',
      }}>
        <h2 style={{
          fontSize: '17px',
          fontWeight: 600,
          color: 'var(--text)',
          letterSpacing: '-0.01em',
          margin: 0,
          flex: 1,
          minWidth: '160px',
        }}>
          {t('calc.title')}
        </h2>

        {/* Toggle Simulador / Optimizador */}
        <div
          role="tablist"
          aria-label={t('calc.modeToggle')}
          style={{
            display: 'flex',
            borderRadius: 'var(--radius-sm)',
            overflow: 'hidden',
            border: '1px solid var(--border-strong)',
            flexShrink: 0,
          }}
        >
          {[
            { id: 'simulator', labelKey: 'calc.mode.simulator' },
            { id: 'optimizer', labelKey: 'calc.mode.optimizer' },
          ].map(({ id, labelKey }) => {
            const isActive = mode === id
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setMode(id)}
                style={{
                  height: '32px',
                  padding: '0 14px',
                  border: 'none',
                  background: isActive ? 'var(--btn-primary-bg)' : 'var(--surface-2)',
                  color: isActive ? 'var(--btn-primary-text)' : 'var(--text-secondary)',
                  fontSize: '13px',
                  fontWeight: isActive ? 600 : 400,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  letterSpacing: '-0.01em',
                  transition: 'background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease)',
                  outline: 'none',
                }}
                onFocus={e => { e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '-2px' }}
                onBlur={e => { e.currentTarget.style.outline = 'none' }}
              >
                {t(labelKey)}
              </button>
            )
          })}
        </div>
      </div>

      {/* ── MODO SIMULADOR ── */}
      {mode === 'simulator' && (
        <>
          {/* ── Panel atacante ── */}
          <ArmyPanel
            role="attacker"
            panelId="calc-atk"
            tribe={atkTribe}
            availableTribes={ATTACKER_TRIBES}
            onTribeChange={(id) => {
              setAtkTribe(id)
              setAtkTroopValues(emptyTroopValues())
            }}
            troops={troopsMap[atkTribe] ?? []}
            troopValues={atkTroopValues}
            onTroopChange={(ordinal, field, value) => {
              setAtkTroopValues(prev => ({
                ...prev,
                [ordinal]: { ...(prev[ordinal] ?? { qty: 0, smithy: 0 }), [field]: value },
              }))
            }}
            attackType={atkType}
            onAttackTypeChange={setAtkType}
            allianceBonusAtk={atkAllianceBonus}
            onAllianceBonusAtk={setAtkAllianceBonus}
            artifactType={atkArtifact}
            onArtifactChange={setAtkArtifact}
            heroPoints={atkHeroPoints}
            onHeroPoints={setAtkHeroPoints}
            heroBonusPct={atkHeroBonusPct}
            onHeroBonusPct={setAtkHeroBonusPct}
          />

          {/* ── Panel defensor ── */}
          <ArmyPanel
            role="defender"
            panelId="calc-def"
            tribe={defState.tribe}
            availableTribes={DEFENDER_TRIBES}
            onTribeChange={(id) => {
              updateDefState({ tribe: id, troopValues: emptyTroopValues() })
            }}
            troops={troopsMap[defState.tribe] ?? []}
            troopValues={defState.troopValues}
            onTroopChange={updateDefTroopValue}
            wallLevel={defState.wallLevel}
            onWallChange={(n) => updateDefState({ wallLevel: n })}
            stonemasonLevel={defState.stonemasonLevel}
            onStonemasonChange={(n) => updateDefState({ stonemasonLevel: n })}
            allianceBonusDef={defState.allianceBonus}
            onAllianceBonusDef={(n) => updateDefState({ allianceBonus: n })}
            heroPoints={defState.heroDefPoints}
            onHeroPoints={(n) => updateDefState({ heroDefPoints: n })}
            heroBonusPct={defState.heroDefBonusPct}
            onHeroBonusPct={(n) => updateDefState({ heroDefBonusPct: n })}
          />

          {/* ── Refuerzos ── */}
          {reinforcements.map((reinf, idx) => (
            <ArmyPanel
              key={reinf.id}
              role="reinforcement"
              panelId={`calc-reinf-${reinf.id}`}
              reinforcementIndex={idx + 1}
              onRemove={() => removeReinforcement(reinf.id)}
              tribe={reinf.tribe}
              availableTribes={DEFENDER_TRIBES}
              onTribeChange={(id) => {
                updateReinforcement(reinf.id, { tribe: id, troopValues: emptyTroopValues() })
              }}
              troops={troopsMap[reinf.tribe] ?? []}
              troopValues={reinf.troopValues}
              onTroopChange={(ordinal, field, value) =>
                updateReinforcementTroop(reinf.id, ordinal, field, value)
              }
              wallLevel={reinf.wallLevel}
              onWallChange={(n) => updateReinforcement(reinf.id, { wallLevel: n })}
              stonemasonLevel={reinf.stonemasonLevel}
              onStonemasonChange={(n) => updateReinforcement(reinf.id, { stonemasonLevel: n })}
              allianceBonusDef={reinf.allianceBonus}
              onAllianceBonusDef={(n) => updateReinforcement(reinf.id, { allianceBonus: n })}
              heroPoints={reinf.heroDefPoints}
              onHeroPoints={(n) => updateReinforcement(reinf.id, { heroDefPoints: n })}
              heroBonusPct={reinf.heroDefBonusPct}
              onHeroBonusPct={(n) => updateReinforcement(reinf.id, { heroDefBonusPct: n })}
            />
          ))}

          {/* ── Botón añadir refuerzo ── */}
          <div style={{ marginBottom: '12px' }}>
            <button
              type="button"
              onClick={addReinforcement}
              style={{
                height: '32px',
                padding: '0 14px',
                background: 'transparent',
                border: '1px dashed var(--border-strong)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '13px',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', gap: '6px',
                transition: 'border-color var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease)',
                width: '100%',
                justifyContent: 'center',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = 'var(--accent)'
                e.currentTarget.style.color = 'var(--accent-text)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = 'var(--border-strong)'
                e.currentTarget.style.color = 'var(--text-secondary)'
              }}
            >
              <span aria-hidden="true">+</span>
              {t('calc.addReinforcement')}
            </button>
          </div>

          {/* ── Botón SIMULAR ── */}
          <button
            type="button"
            onClick={handleSimulate}
            disabled={simulating}
            aria-busy={simulating}
            style={{
              height: '40px',
              width: '100%',
              background: simulating ? 'var(--btn-primary-hover)' : 'var(--btn-primary-bg)',
              color: 'var(--btn-primary-text)',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              fontSize: '15px',
              fontWeight: 600,
              cursor: simulating ? 'wait' : 'pointer',
              fontFamily: 'inherit',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              transition: 'background var(--dur-fast) var(--ease)',
              letterSpacing: '-0.01em',
              outline: 'none',
            }}
            onMouseEnter={e => { if (!simulating) e.currentTarget.style.background = 'var(--btn-primary-hover)' }}
            onMouseLeave={e => { if (!simulating) e.currentTarget.style.background = 'var(--btn-primary-bg)' }}
            onFocus={e => { e.currentTarget.style.outline = '2px solid var(--accent)'; e.currentTarget.style.outlineOffset = '2px' }}
            onBlur={e => { e.currentTarget.style.outline = 'none' }}
          >
            {simulating ? (
              <>
                <Spinner size={16} />
                {t('calc.simulating')}
              </>
            ) : (
              t('calc.simulate')
            )}
          </button>

          {/* ── Resultado simulador ── */}
          <CombatResult
            result={result?.response ?? null}
            attackerTribeTroops={troopsMap[atkTribe] ?? []}
            defenderFormations={result?.defenderFormations ?? null}
          />
        </>
      )}

      {/* ── MODO OPTIMIZADOR ── */}
      {mode === 'optimizer' && (
        <>
          <OptimizerPanel
            atkTribe={atkTribe}
            onAtkTribeChange={(id) => {
              setAtkTribe(id)
              setAtkTroopValues(emptyTroopValues())
            }}
            troops={troopsMap[atkTribe] ?? []}
            natureTroops={troopsMap['nature'] ?? []}
            onOptimize={handleOptimize}
            optimizing={optimizing}
            onInputModeChange={setOptimizerInputMode}
            onMinNetGainPctChange={setOptimizerMinNetGainPct}
          />
          <OptimizerResult
            result={optResult}
            troopMeta={troopsMap[atkTribe] ?? []}
            natureTroops={troopsMap['nature'] ?? []}
            inputMode={optimizerInputMode}
            minNetGainPct={optimizerMinNetGainPct}
          />
        </>
      )}
    </div>
  )
}
