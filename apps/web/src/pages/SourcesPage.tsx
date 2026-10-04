import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { Actor } from '../auth/client';
import { CollectorControls } from '../sources/CollectorControls';
import { SourceRegistrationForm } from '../sources/SourceRegistrationForm';
import type { SourceRegistration } from '../sources/client';
import { queries, type Source } from '../api/client';
import { Empty, ReadState, Status, timestamp } from '../components/ReadState';
import { link, useRoute } from '../navigation';

const missingFields = ['version', 'schema', 'errors'] as const;
const columns = ['name', 'type', 'state', 'lag', 'cursor'] as const;

export function Pager({ total, offset }: { total: number; offset: number }) {
  const { t } = useTranslation();
  const route = useRoute();
  const change = (next: number) => { const values = Object.fromEntries(route.params); window.location.hash = link(route.section, { ...values, offset: next }); };
  return <div className="pager"><button disabled={offset === 0} onClick={() => change(Math.max(0, offset - 50))}>{t('common.previous')}</button>
    <span>{t('common.page', { start: offset < total ? offset + 1 : 0, end: offset < total ? Math.min(offset + 50, total) : 0, total })}</span>
    <button disabled={offset + 50 >= total || offset + 50 > 1000000} onClick={() => change(offset + 50)}>{t('common.next')}</button></div>;
}
function SourceEvidence({ source }: { source: Source }) {
  const { t, i18n } = useTranslation();
  const fresh = source.freshness;
  return <dl><dt>{t('sources.state')}</dt><dd><Status state={fresh.state} /></dd>
    <dt>{t('sources.heartbeat')}</dt><dd>{timestamp(fresh.last_collector_at, i18n.language) ?? t('common.unavailable')}</dd>
    <dt>{t('sources.event')}</dt><dd>{timestamp(fresh.last_event_at, i18n.language) ?? t('common.unavailable')}</dd>
    <dt>{t('sources.lag')}</dt><dd>{fresh.lag_seconds ?? t('common.unavailable')}</dd>
    <dt>{t('sources.cursor')}</dt><dd><code>{fresh.cursor ?? t('common.unavailable')}</code></dd>
    <dt>{t('sources.collectors', { count: fresh.collector_count })}</dt><dd>{t('sources.unknownCollectors', { count: fresh.unknown_collector_count })}</dd>
    {missingFields.map(key => <div key={key}><dt>{t(`sources.${key}`)}</dt><dd>{t('common.unavailable')}</dd></div>)}
  </dl>;
}
type Authority = { actor?: Actor; onPermissionDenied?: () => void };
function SourceDetail({ id, actor, onPermissionDenied }: { id: string } & Authority) {
  const { t } = useTranslation();
  const query = useQuery({ ...queries.source(id), retry: false });
  return <ReadState query={query}>{query.data ? <article><h2>{query.data.hostname}</h2><code>{query.data.id}</code><SourceEvidence source={query.data} /><a href={link('health', { source_id: id, tab: 'volumes' })}>{t('storage.volumes')}</a><CollectorControls source={query.data} actor={actor} onPermissionDenied={onPermissionDenied} /></article> : null}</ReadState>;
}
export function SourcesPage(props: Authority) {
  return <SourcesContent key={`${props.actor?.id ?? ''}:${props.actor?.roles.join(',') ?? ''}`} {...props} />;
}
function SourcesContent({ actor, onPermissionDenied }: Authority) {
  const route = useRoute();
  const cache = useQueryClient(); const [blocked, setBlocked] = useState(false);
  const deny = () => { setBlocked(true); onPermissionDenied?.(); };
  const refresh = () => {
    void cache.invalidateQueries({ queryKey: ['sources'] });
    void cache.invalidateQueries({ queryKey: ['overview'] });
  };
  const created = (source: SourceRegistration) => {
    refresh();
    window.location.hash = link('sources', { id: source.id });
  };
  const id = route.params.get('id');
  return id ? <SourceDetail key={id} id={id} actor={blocked ? undefined : actor} onPermissionDenied={deny} /> : <>
    <SourceList offset={route.offset} />
    {actor?.roles.includes('storage_admin') && !blocked ? <SourceRegistrationForm onPermissionDenied={deny} onUnconfirmed={refresh} onCreated={created} /> : null}
  </>;
}
function SourceList({ offset }: { offset: number }) {
  const { t } = useTranslation();
  const query = useQuery({ ...queries.sources({ limit: 50, offset }), retry: false });
  return <ReadState query={query}>{query.data ? <>
    {query.data.items.length ? <div className="table-scroll"><table><thead><tr>
      {columns.map(key => <th key={key} scope="col">{t(`sources.${key}`)}</th>)}
    </tr></thead><tbody>{query.data.items.map(source => <tr key={source.id}><td><a href={link('sources', { id: source.id })}>{source.hostname}</a></td><td>{t(`sourceTypes.${source.source_type}`)}</td><td><Status state={source.freshness.state} /></td><td>{source.freshness.lag_seconds ?? t('common.unavailable')}</td><td><code>{source.freshness.cursor ?? t('common.unavailable')}</code></td></tr>)}</tbody></table></div> : <Empty />}
    <Pager total={query.data.total} offset={offset} />
  </> : null}</ReadState>;
}
