import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { queries } from '../api/client';
import { ReadState, Status, timestamp } from '../components/ReadState';

const domains = ['TELEMETRY', 'CAPACITY', 'FILESYSTEM', 'SMB_DFS', 'ACCESS', 'VSS', 'RECOVERY', 'NETWORK', 'PVE_ZFS', 'HYGIENE'] as const;
export function OverviewPage() {
  const { t, i18n } = useTranslation();
  const query = useQuery({ ...queries.overview(), retry: false });
  const data = query.data;
  return <ReadState query={query}>{data ? <>
    <div className="counts">
      <p>{t('overview.sources')}: {data.counts.sources}</p><p>{t('overview.volumes')}: {data.counts.volumes}</p>
      <p>{t('overview.shares')}: {data.counts.shares}</p><p>{t('overview.objects')}: {data.counts.filesystem_objects}</p>
      <p>{t('overview.warnings', { count: data.domains.filter(item => item.state === 'WARNING').length })}</p>
      <p>{t('overview.critical', { count: data.domains.filter(item => item.state === 'CRITICAL').length })}</p>
    </div>
    <section className="cards" aria-label={t('overview.storage')}>
      <article><h2>{t('overview.overall')}</h2><Status state={data.overall_state} />
        <p>{t('overview.unknownDomains', {count:data.domains.filter(item=>item.state==='UNKNOWN').length,total:domains.length})}</p>
      </article>
      <article><h2>{t('overview.freshness')}</h2><Status state={data.freshness.state} />
        <p>{t('overview.currentSources', {count:data.freshness.current_source_count,total:data.freshness.source_count})}</p>
        <p>{t('overview.staleSources', {count:data.freshness.stale_source_count})}</p>
        <p>{t('overview.unknownSources', {count:data.freshness.unknown_source_count})}</p>
        <p>{t('overview.lastReceived')}: {timestamp(data.freshness.last_received_at,i18n.language) ?? t('common.unavailable')}</p>
        <p>{t('overview.oldestEvent')}: {timestamp(data.freshness.oldest_event_at,i18n.language) ?? t('common.unavailable')}</p>
      </article>
      {domains.map(domain => {
        const finding = data.domains.find(item => item.domain === domain);
        return <article key={domain}><h2>{t(`domains.${domain}`)}</h2><Status state={finding?.state ?? 'UNKNOWN'} />
          <p>{t('overview.unknownCoverage', { unknown: finding?.unknown_source_count ?? data.counts.sources, total: finding?.source_count ?? data.counts.sources })}</p>
        </article>;
      })}
    </section>
  </> : null}</ReadState>;
}
