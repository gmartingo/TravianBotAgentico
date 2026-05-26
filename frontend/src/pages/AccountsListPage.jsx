/**
 * AccountsListPage — placeholder S2 (Etapa 1).
 * Contenido real se implementa en Etapa 2.
 */
import { useI18n } from '../i18n/index.jsx'

export function AccountsListPage() {
  const { t } = useI18n()

  return (
    <div className="p-6 lg:p-8">
      <h1 className="text-[28px] font-semibold tracking-[-0.02em] text-[var(--text)] mb-2">
        {t('page.accounts.title')}
      </h1>
      <p className="text-[var(--text-secondary)] text-[13px] mt-4 p-4 bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-md)]">
        {t('placeholder.accounts.list')}
      </p>
    </div>
  )
}
