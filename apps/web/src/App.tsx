import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

const sections = ['overview', 'health', 'activity', 'access', 'recovery', 'hygiene', 'diagnostics', 'discovery', 'sources', 'policies', 'settings', 'audit'] as const;

async function readiness(): Promise<boolean> {
  const response = await fetch('/ready', { signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error('API_UNAVAILABLE');
  const data: unknown = await response.json();
  if (!data || typeof data !== 'object' || !('status' in data) || data.status !== 'ok') throw new Error('API_UNAVAILABLE');
  return true;
}

export function App() {
  const { t } = useTranslation();
  const [section, setSection] = useState<(typeof sections)[number]>('overview');
  const api = useQuery({ queryKey: ['readiness'], queryFn: readiness, refetchInterval: 30000, retry: false });
  return <div className="layout">
    <aside className="sidebar">
      <div className="brand">{t('app.name')}</div>
      <p className="subtitle">{t('app.subtitle')}</p>
      <nav aria-label={t('navigation.label')}>
        {sections.map(item => <button key={item} aria-current={section === item ? 'page' : undefined} onClick={() => setSection(item)}>{t(`navigation.${item}`)}</button>)}
      </nav>
      <p className="boundary">{t('app.boundary')}</p>
    </aside>
    <main>
      <header><span>{t('runtime.label')}</span><span role="status" className={api.isError ? 'runtime error' : 'runtime'}>{t(api.isPending ? 'common.loading' : api.isError ? 'runtime.unavailable' : 'runtime.available')}</span>{api.isError ? <button onClick={() => void api.refetch()}>{t('common.retry')}</button> : null}</header>
      <div className="content">
        <h1>{t(`navigation.${section}`)}</h1>
        <p className="notice">{t('app.foundation')}</p>
        <section className="cards" aria-label={t('overview.storage')}>
          <article><h2>{t('overview.storage')}</h2><p className="unknown">{t('health.UNKNOWN')}</p><p>{t('common.empty')}</p></article>
          <article><h2>{t('overview.freshness')}</h2><p>{t('common.empty')}</p></article>
          <article><h2>{t('overview.mode')}</h2><p>{t('overview.noMutation')}</p></article>
        </section>
      </div>
    </main>
  </div>;
}
