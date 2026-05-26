/**
 * AccountDetailPage — placeholder S4 (Etapa 1).
 * Contenido real se implementa en Etapa 2.
 */
import { useParams, Link } from 'react-router-dom'
import { useI18n } from '../i18n/index.jsx'

export function AccountDetailPage() {
  const { id } = useParams()
  const { t } = useI18n()

  return (
    <div className="p-6 lg:p-8">
      {/* Breadcrumb mínimo */}
      <nav aria-label="Migas de pan" className="mb-4">
        <Link
          to="/cuentas"
          className="text-[var(--accent-text)] hover:text-[var(--accent-hover)] text-[13px]"
        >
          ← {t('page.account.breadcrumb')}
        </Link>
      </nav>

      <h1 className="text-[28px] font-semibold tracking-[-0.02em] text-[var(--text)] mb-2">
        {t('page.account.breadcrumb')} #{id}
      </h1>
      <p className="text-[var(--text-secondary)] text-[13px] mt-4 p-4 bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-md)]">
        {t('placeholder.account.detail')}
      </p>
    </div>
  )
}
