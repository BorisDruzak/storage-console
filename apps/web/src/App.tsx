import { useEffect,useRef,type ComponentType } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { queries } from './api/client';
import { useExpiredEvidence } from './api/evidence';
import { timestamp } from './components/ReadState';
import { sections, link, useRoute, type Section } from './navigation';
import { OverviewPage } from './pages/OverviewPage';
import { SourcesPage } from './pages/SourcesPage';
import { StoragePage } from './pages/StoragePage';
import { ActivityPage } from './pages/ActivityPage';
import { RecoveryPage } from './pages/RecoveryPage';
import { AccessPage, HygienePage, DiagnosticsPage, DiscoveryPage, PoliciesPage, AuditPage } from './pages/ReadDomains';
import { SettingsPage } from './pages/SettingsPage';
import { usePreferences } from './preferences';
import { SessionProvider } from './auth/SessionProvider';
import { AuthGate } from './auth/LoginPage';

const pages:Partial<Record<Section,ComponentType>>={
  overview:OverviewPage,sources:SourcesPage,health:StoragePage,activity:ActivityPage,recovery:RecoveryPage,
  access:AccessPage,hygiene:HygienePage,diagnostics:DiagnosticsPage,discovery:DiscoveryPage,policies:PoliciesPage,audit:AuditPage,
  settings:SettingsPage,
};

async function readiness({ signal }: { signal: AbortSignal }): Promise<boolean> {
  const response = await fetch('/ready', { signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]) });
  if (!response.ok) throw new Error('API_UNAVAILABLE');
  const data: unknown = await response.json();
  if (!data || typeof data !== 'object' || !('status' in data) || data.status !== 'ok') throw new Error('API_UNAVAILABLE');
  return true;
}

export function ConsoleShell() {
  const { t, i18n } = useTranslation();
  const { section } = useRoute();
  const preferences=usePreferences();const heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{heading.current?.focus();},[section]);
  useEffect(()=>{void i18n.changeLanguage(preferences.locale);},[preferences.locale,i18n]);
  useEffect(()=>{document.documentElement.lang=i18n.language;document.title=t('app.name');},[i18n.language,t]);
  const Page=pages[section];
  const api = useQuery({ queryKey: ['readiness'], queryFn: readiness, refetchInterval: 30000, retry: false });
  const overview = useQuery({ ...queries.overview(), retry: false });
  const overviewExpired=useExpiredEvidence(overview.data);
  return <div className="layout">
    <a className="skip-link" href="#main-content" onClick={event=>{event.preventDefault();heading.current?.focus();}}>{t('common.skip')}</a>
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
        <span>{overview.isError ? t('common.error') : overviewExpired ? t('common.expired') : overview.data ? t('overview.evaluated', { at: timestamp(overview.data.evaluated_at, i18n.language) }) : t('common.loading')}</span>
      </header>
      <div className="content">
        <h1 id="main-content" ref={heading} tabIndex={-1}>{t(`navigation.${section}`)}</h1>
        {Page?<Page />:<p>{t('common.unavailableEvidence')}</p>}
      </div>
    </main>
  </div>;
}

export function App() {
  return <SessionProvider><AuthGate><ConsoleShell /></AuthGate></SessionProvider>;
}
