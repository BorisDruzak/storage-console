import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { queries } from './api/client';
import { timestamp } from './components/ReadState';
import { sections, link, useRoute } from './navigation';
import { OverviewPage } from './pages/OverviewPage';
import { SourcesPage } from './pages/SourcesPage';
import { StoragePage } from './pages/StoragePage';
import { ActivityPage } from './pages/ActivityPage';
import { RecoveryPage } from './pages/RecoveryPage';

async function readiness({ signal }: { signal: AbortSignal }): Promise<boolean> {
  const response = await fetch('/ready', { signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]) });
  if (!response.ok) throw new Error('API_UNAVAILABLE');
  const data: unknown = await response.json();
  if (!data || typeof data !== 'object' || !('status' in data) || data.status !== 'ok') throw new Error('API_UNAVAILABLE');
  return true;
}

export function App() {
  const { t, i18n } = useTranslation();
  const { section } = useRoute();
  const api = useQuery({ queryKey: ['readiness'], queryFn: readiness, refetchInterval: 30000, retry: false });
  const overview = useQuery({ ...queries.overview(), retry: false });
  return <div className="layout">
    <aside className="sidebar">
      <div className="brand">{t('app.name')}</div>
      <p className="subtitle">{t('app.subtitle')}</p>
      <nav aria-label={t('navigation.label')}>
        {sections.map(item => <a key={item} aria-current={section === item ? 'page' : undefined} href={link(item)}>{t(`navigation.${item}`)}</a>)}
      </nav>
      <p className="boundary">{t('app.boundary')}</p>
    </aside>
    <main>
      <header><span>{t('runtime.label')}</span><span role="status" className={api.isError ? 'runtime error' : 'runtime'}>{t(api.isPending ? 'common.loading' : api.isError ? 'runtime.unavailable' : 'runtime.available')}</span>{api.isError ? <button onClick={() => void api.refetch()}>{t('common.retry')}</button> : null}
        <span>{overview.isError ? t('common.error') : overview.data ? t('overview.evaluated', { at: timestamp(overview.data.evaluated_at, i18n.language) }) : t('common.loading')}</span>
      </header>
      <div className="content">
        <h1 tabIndex={-1}>{t(`navigation.${section}`)}</h1>
        {section === 'overview' ? <OverviewPage /> : section === 'sources' ? <SourcesPage /> : section === 'health' ? <StoragePage /> : section === 'activity' ? <ActivityPage /> : section === 'recovery' ? <RecoveryPage /> : <p>{t('common.unavailableEvidence')}</p>}
      </div>
    </main>
  </div>;
}
