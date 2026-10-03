import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { queries } from '../api/client';
import { Empty, ReadState } from '../components/ReadState';
import { link, useRoute } from '../navigation';
import { Pager, SourcesPage } from './SourcesPage';

const tabs = ['fileserver', 'volumes', 'smb', 'dfs', 'fsrm', 'vss', 'pve', 'network'] as const;
function SourceFilter({ source, tab }: { source: string; tab: string }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(source);
  useEffect(() => {
    // Apply/back can return to the same snapshot before React renders the middle route.
    const restore = () => setDraft(new URLSearchParams(window.location.hash.split('?')[1]).get('source_id') ?? '');
    window.addEventListener('hashchange', restore);
    return () => window.removeEventListener('hashchange', restore);
  }, []);
  return <form onSubmit={event => { event.preventDefault(); window.location.hash = link('health', { tab, ...(draft.trim() ? { source_id: draft.trim() } : {}) }); }}><label>{t('common.sourceFilter')}<input value={draft} onChange={event => setDraft(event.target.value)} /></label><button type="submit">{t('common.apply')}</button></form>;
}
function Volumes({ shares }: { shares: boolean }) {
  const { t } = useTranslation();
  const route = useRoute();
  const filters = { limit: 50, offset: route.offset, source_id: route.params.get('source_id') || undefined };
  const volumes = useQuery({ ...queries.volumes(filters), enabled: !shares, retry: false });
  const shareData = useQuery({ ...queries.shares(filters), enabled: shares, retry: false });
  const query = shares ? shareData : volumes;
  return <ReadState query={query}>{query.data ? <>
    {query.data.items.length ? <div className="table-scroll"><table><thead><tr>
      <th scope="col">{t('storage.name')}</th><th scope="col">{t(shares ? 'storage.path' : 'storage.aliases')}</th>
      {!shares ? <><th scope="col">{t('storage.total')}</th><th scope="col">{t('storage.free')}</th></> : null}
      <th scope="col">{t('storage.quality')}</th>
    </tr></thead><tbody>{shares ? shareData.data?.items.map(item => <tr key={item.id}><td>{item.name}</td><td><code>{item.relative_path}</code></td><td>{t(`quality.${item.quality}`)}</td></tr>) : volumes.data?.items.map(item => <tr key={item.id}><td>{item.label ?? item.unique_identity}<small><code>{item.unique_identity}</code></small></td><td><code>{item.mount_aliases.join(', ') || t('common.unavailable')}</code></td><td>{item.total_bytes?.toLocaleString() ?? t('common.unavailable')}</td><td>{item.free_bytes?.toLocaleString() ?? t('common.unavailable')}</td><td>{t(`quality.${item.quality}`)}</td></tr>)}</tbody></table></div> : <Empty />}
    <Pager total={query.data.total} offset={route.offset} />
  </> : null}</ReadState>;
}
export function StoragePage() {
  const { t } = useTranslation();
  const route = useRoute();
  const tab = tabs.find(item => item === route.params.get('tab')) ?? 'fileserver';
  const source = route.params.get('source_id') ?? '';
  return <>
    <nav className="tabs" aria-label={t('navigation.health')}>{tabs.map(item => <a key={item} aria-current={tab === item ? 'page' : undefined} href={link('health', { tab: item, ...(source ? { source_id: source } : {}) })}>{t(`storage.${item}`)}</a>)}</nav>
    {tab === 'volumes' || tab === 'smb' ? <SourceFilter key={source} source={source} tab={tab} /> : null}
    {tab === 'fileserver' ? <SourcesPage /> : tab === 'volumes' || tab === 'smb' ? <Volumes shares={tab === 'smb'} /> : <p>{t('common.unavailableEvidence')}</p>}
  </>;
}
