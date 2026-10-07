import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { queries } from '../api/client';
import { ReadState, Status, timestamp } from '../components/ReadState';
import { formatBytes } from '../formatBytes';

const domains = ['TELEMETRY', 'CAPACITY', 'FILESYSTEM', 'SMB_DFS', 'ACCESS', 'VSS', 'RECOVERY', 'NETWORK', 'PVE_ZFS', 'HYGIENE'] as const;
export function OverviewPage() {
  const { t, i18n } = useTranslation();
  const query = useQuery({ ...queries.overview(), retry: false });
  const data = query.data;
  const percent = data?.capacity.used_percent;
  const utilization = percent === undefined || percent === null ? t('common.unavailable') :
    new Intl.NumberFormat(i18n.language,{style:'percent',maximumFractionDigits:2}).format(percent / 100);
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
        if (domain === 'CAPACITY') return <article key={domain}>
          <h2>{t('domains.CAPACITY')}</h2><Status state={data.capacity.state} />
          <p>{t('overview.capacityMeasured')}</p>
          <p>{t('overview.used')}: {formatBytes(data.capacity.used_bytes,i18n.language,t)}</p>
          <p>{t('storage.free')}: {formatBytes(data.capacity.free_bytes,i18n.language,t)}</p>
          <p>{t('storage.total')}: {formatBytes(data.capacity.total_bytes,i18n.language,t)}</p>
          <p>{t('overview.usedPercent')}: {utilization}</p>
          <p>{t('overview.currentVolumes',{count:data.capacity.current_volume_count,total:data.capacity.volume_count})}</p>
          <p>{t('overview.unavailableVolumes',{count:data.capacity.unavailable_volume_count})}</p>
          <p>{t('overview.latestInventory')}: {timestamp(data.capacity.latest_inventory_at,i18n.language) ?? t('common.unavailable')}</p>
        </article>;
        if (domain === 'FILESYSTEM') return <article key={domain}>
          <h2>{data.inventory.filesystem_types.length ? t('overview.filesystemTitle',{types:data.inventory.filesystem_types.join(', ')}) : t('domains.FILESYSTEM')}</h2>
          <Status state={finding?.state ?? 'UNKNOWN'} />
          <p>{t('overview.detectedVolumes',{count:data.inventory.volume_count})}</p>
          <p>{t('overview.filesystemTypes')}: {data.inventory.filesystem_types.join(', ') || t('common.unavailable')}</p>
          <p>{t('overview.latestInventory')}: {timestamp(data.inventory.latest_inventory_at,i18n.language) ?? t('common.unavailable')}</p>
          <p>{t('overview.integrityUnavailable')}</p>
          <p>{t('overview.inventoryFacts')}</p>
        </article>;
        return <article key={domain}><h2>{t(`domains.${domain}`)}</h2><Status state={finding?.state ?? 'UNKNOWN'} />
          <p>{t('overview.unknownCoverage', { unknown: finding?.unknown_source_count ?? data.counts.sources, total: finding?.source_count ?? data.counts.sources })}</p>
        </article>;
      })}
    </section>
  </> : null}</ReadState>;
}
