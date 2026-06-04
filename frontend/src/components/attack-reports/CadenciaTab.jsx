/**
 * CadenciaTab — Pestaña "Cadencia de farmeo" del módulo de reportes de oasis.
 *
 * Propietaria del estado y fetch de AnimalFrequencyPanel (EP-TD).
 * Se monta de forma lazy (solo cuando el tab está activo), igual que StatsTab.
 *
 * Props:
 *   lang          — código de idioma activo
 *   onGoToIngest  — callback para navegar al tab "Ingresar"
 */
import { useState, useEffect, useCallback } from 'react'
import { useI18n } from '../../i18n/index.jsx'
import { api } from '../../api/client.js'
import { AnimalFrequencyPanel } from './AnimalFrequencyPanel.jsx'

const DEFAULT_INTERVAL_MIN = 240  // 4h por defecto (spec §7.5)

export function CadenciaTab({ lang, onGoToIngest }) {
  const { t } = useI18n()

  // ── Estado AnimalFrequencyPanel (EP-TD) ───────────────────────────────────
  const [freqIntervalMin, setFreqIntervalMin] = useState(DEFAULT_INTERVAL_MIN)
  const [freqData, setFreqData]               = useState(null)
  const [freqLoading, setFreqLoading]         = useState(true)
  const [freqError, setFreqError]             = useState(null)

  const loadFreq = useCallback(async (interval) => {
    setFreqLoading(true)
    setFreqError(null)
    try {
      const res = await api.getAnimalTemporalDistribution(interval)
      setFreqData(res)
    } catch (err) {
      setFreqError(err?.detail ?? t('ar.freq.error'))
      setFreqData(null)
    } finally {
      setFreqLoading(false)
    }
  }, [t])

  useEffect(() => { loadFreq(freqIntervalMin) }, [loadFreq, freqIntervalMin])

  const handleFreqIntervalChange = useCallback((newInterval) => {
    setFreqIntervalMin(newInterval)
  }, [])

  const retryFreq = useCallback(() => {
    loadFreq(freqIntervalMin)
  }, [loadFreq, freqIntervalMin])

  return (
    <div style={{ maxWidth: '900px' }}>
      <AnimalFrequencyPanel
        data={freqData}
        loading={freqLoading}
        error={freqError}
        intervalMinutes={freqIntervalMin}
        onIntervalChange={handleFreqIntervalChange}
        onRetry={retryFreq}
        onGoToIngest={onGoToIngest}
        lang={lang}
        t={t}
      />
    </div>
  )
}
