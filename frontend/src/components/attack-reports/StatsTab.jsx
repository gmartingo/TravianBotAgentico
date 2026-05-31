/**
 * StatsTab — Pestaña "Estadísticas" del módulo de reportes de oasis.
 *
 * Rediseño completo: en vez de un formulario de coordenadas, muestra directamente
 * la lista navegable de oasis (OasisList) que se carga automáticamente.
 *
 * La lógica de carga, filtro, expand y estados está encapsulada en OasisList.
 *
 * Props:
 *   lang         — string (idioma activo)
 *   onGoToIngest — () => void — callback para navegar a la pestaña Ingresar
 *                  (CTA del estado vacío y navegación desde OasisList)
 */
import { useI18n } from '../../i18n/index.jsx'
import { OasisList } from './OasisList.jsx'

export function StatsTab({ lang, onGoToIngest }) {
  const { t } = useI18n()

  return (
    <div style={{ maxWidth: '900px' }}>
      <OasisList
        lang={lang}
        onGoToIngest={onGoToIngest}
        t={t}
      />
    </div>
  )
}
