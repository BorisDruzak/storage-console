import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { queries } from '../api/client';
import { ReadState, Status } from '../components/ReadState';

const domains = ['TELEMETRY', 'CAPACITY', 'FILESYSTEM', 'SMB_DFS', 'ACCESS', 'VSS', 'RECOVERY', 'NETWORK', 'PVE_ZFS', 'HYGIENE'] as const;
export function OverviewPage() {
  const { t } = useTranslation();
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
      {domains.map(domain => {
        const finding = data.domains.find(item => item.domain === domain);
        return <article key={domain}><h2>{t(`domains.${domain}`)}</h2><Status state={finding?.state ?? 'UNKNOWN'} />
          <p>{t('overview.unknownCoverage', { unknown: finding?.unknown_source_count ?? data.counts.sources, total: finding?.source_count ?? data.counts.sources })}</p>
        </article>;
      })}
    </section>
  </> : null}</ReadState>;
}
