/**
 * StatsTab — Pestaña "Estadísticas" del módulo de reportes de oasis.
 *
 * Layout v2.2 (orden aprobado por el usuario):
 *   1. SpawnMechanicsPanel       — educativo/estático, colapsable
 *   2. BalanceSection            — pérdidas/ganancias del mundo
 *   3. OasisCombatPlannerPanel   — combinaciones por oasis (Media/Peor, sin def)
 *   4. GlobalOasisStatsPanel     — apariciones globales
 *   5. OasisList                 — lista navegable de oasis
 *
 * Carga independiente: un error en cualquier panel NO bloquea los demás.
 * SpawnMechanicsPanel: sin carga (datos estáticos del catálogo).
 * OasisCombatPlannerPanel: EP-SPAWN re-lanzado cuando cambia timerMin.
 *
 * Flujo 5.3: si la respuesta EP-SPAWN es oasis:[], vacíoBD=true se pasa a
 * SpawnMechanicsPanel para que se despliegue automáticamente.
 */
import { useState, useEffect, useCallback } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api } from '../../api/client.js'
import { OasisList } from './OasisList.jsx'
import { GlobalOasisStatsPanel } from './GlobalOasisStatsPanel.jsx'
import { BalanceSection } from './BalanceSection.jsx'
import { SpawnMechanicsPanel } from './SpawnMechanicsPanel.jsx'
import { OasisCombatPlannerPanel } from './OasisCombatPlannerPanel.jsx'
// AnimalFrequencyPanel: pendiente de implementación.
// Bloqueada hasta spec de diseño del agente disenador-producto + mockup editable aprobado.
// Ver spec docs/specs/bd-ataques-oasis-temporal-distribution.md §3 y §14 paso 5.
// import { AnimalFrequencyPanel } from './AnimalFrequencyPanel.jsx'

const DEFAULT_TIMER_MIN = 10  // valor por defecto (spec §14 decisión)

export function StatsTab({ lang, onGoToIngest }) {
  const { t } = useI18n()

  // ── Estado panel global (independiente) ───────────────────────────────────
  const [globalData, setGlobalData]       = useState(null)
  const [globalLoading, setGlobalLoading] = useState(true)
  const [globalError, setGlobalError]     = useState(null)

  const loadGlobal = useCallback(async () => {
    setGlobalLoading(true)
    setGlobalError(null)
    try {
      const res = await api.getGlobalOasisStats()
      setGlobalData(res)
    } catch (err) {
      setGlobalError(err?.detail ?? t('ar.stats.global.error'))
    } finally {
      setGlobalLoading(false)
    }
  }, [t])

  useEffect(() => { loadGlobal() }, [loadGlobal])

  // ── Estado EP-SPAWN (OasisCombatPlannerPanel) ──────────────────────────────
  const [timerMin, setTimerMin]         = useState(DEFAULT_TIMER_MIN)
  const [spawnData, setSpawnData]       = useState(null)
  const [spawnLoading, setSpawnLoading] = useState(true)
  const [spawnError, setSpawnError]     = useState(null)

  const loadSpawn = useCallback(async (timer) => {
    setSpawnLoading(true)
    setSpawnError(null)
    try {
      const res = await api.getOasisSpawnComposition(timer)
      setSpawnData(res)
    } catch (err) {
      setSpawnError(err?.detail ?? t('stats.planner.error'))
      setSpawnData(null)
    } finally {
      setSpawnLoading(false)
    }
  }, [t])

  useEffect(() => { loadSpawn(timerMin) }, [loadSpawn, timerMin])

  const handleTimerChange = useCallback((newTimer) => {
    setTimerMin(newTimer)
  }, [])

  const retrySpawn = useCallback(() => {
    loadSpawn(timerMin)
  }, [loadSpawn, timerMin])

  // ¿La BD está vacía? Para el auto-despliegue de SpawnMechanicsPanel (flujo 5.3)
  const vacíoBD = !spawnLoading && !spawnError && spawnData != null && spawnData.oasis.length === 0

  return (
    <div style={{ maxWidth: '900px' }}>

      {/* 1. SpawnMechanicsPanel — educativo, estático, colapsable */}
      <SpawnMechanicsPanel lang={lang} t={t} vacíoBD={vacíoBD} />

      {/* 2. BalanceSection — pérdidas/ganancias del mundo */}
      <BalanceSection lang={lang} t={t} />

      {/* 3. OasisCombatPlannerPanel — dos filas Media/Peor por oasis */}
      <OasisCombatPlannerPanel
        data={spawnData}
        loading={spawnLoading}
        error={spawnError}
        onRetry={retrySpawn}
        onGoToIngest={onGoToIngest}
        timerMin={timerMin}
        onTimerChange={handleTimerChange}
        lang={lang}
        t={t}
      />

      {/* Separador antes de los paneles existentes */}
      <hr
        style={{
          border: 'none',
          borderTop: '1px solid var(--border)',
          margin: '8px 0 24px 0',
        }}
      />

      {/* 4. Panel global de estadísticas */}
      <GlobalOasisStatsPanel
        data={globalData}
        loading={globalLoading}
        error={globalError}
        onRetry={loadGlobal}
        onGoToIngest={onGoToIngest}
        lang={lang}
        t={t}
      />

      {/* 5. Lista de oasis individuales */}
      <OasisList
        lang={lang}
        onGoToIngest={onGoToIngest}
        t={t}
      />

      {/* AnimalFrequencyPanel (EP-TD) — TODO: implementar tras spec de diseño aprobado.
          Requiere spec del agente disenador-producto + mockup editable (regla mockup-first).
          Ver spec docs/specs/bd-ataques-oasis-temporal-distribution.md §3 y §14 paso 5. */}
    </div>
  )
}
